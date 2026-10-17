"""Published falsification reports are generated from the actual nine scenarios."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from benchmark.falsification import run_suite as runner
from benchmark.falsification import scenarios as src


@pytest.fixture(scope="module")
def comparative_results():
    return runner.run_suite(src.build_all_scenarios())


def test_falsification_reporting_roundtrips_all_policy_results(comparative_results) -> None:
    cases = src.build_all_scenarios()
    serialized = runner.results_to_dicts(comparative_results)
    assert len(serialized) == 2 * len(cases)
    assert {(row["scenario_id"], row["policy"]) for row in serialized} == {
        (case.id, policy) for case in cases for policy in ("single", "multi")
    }
    assert all(isinstance(row["steps"], list) and row["steps"] for row in serialized)
    for original, encoded in zip(comparative_results, serialized, strict=True):
        assert original.final_answer == encoded["final_answer"]
        assert original.correct == encoded["correct"]
        assert original.total_tokens == encoded["total_tokens"]
        assert encoded["steps"][-1]["leader"] == original.steps[-1].leader
        assert encoded["brier"] is None or 0.0 <= encoded["brier"] <= 2.0


def test_markdown_tables_use_real_comparison_data(comparative_results) -> None:
    aggregate = runner.aggregate(comparative_results)
    text = runner.render_markdown_table(aggregate, comparative_results)
    assert text.startswith("## Aggregate summary")
    assert "overall accuracy" in text
    assert "Per-scenario results" in text
    assert "Brier score" in text
    for case in src.build_all_scenarios():
        assert case.id in text
    assert len([line for line in text.splitlines() if line.startswith("| ")]) >= 23
    assert "nan" not in text.lower()


def test_report_helpers_format_each_truthful_tristate() -> None:
    fake = runner.ScenarioResult(
        scenario_id="case",
        scenario_type="control",
        policy="single",
        final_answer="H_A",
        truth="H_A",
        correct=True,
        steps=[],
        total_tokens=0,
        total_latency_ms=0.0,
        mean_latency_ms=0.0,
        switch_success=None,
        switch_delay_steps=None,
        wrong_leader_steps=0,
        revival_success=None,
        brier=None,
    )
    assert runner._switch_text(fake) == "n/a"
    assert runner._revival_text(fake) == "n/a"
    fake.switch_success = True
    fake.switch_delay_steps = 2
    fake.revival_success = True
    assert runner._switch_text(fake) == "yes (+2)"
    assert runner._revival_text(fake) == "yes"
    fake.switch_success = False
    fake.revival_success = False
    assert runner._switch_text(fake) == "no"
    assert runner._revival_text(fake) == "no"


def test_empty_metric_values_remain_explicitly_unknown() -> None:
    assert runner._softmax_scores({}) == {}
    assert runner._brier_from_rows([]) == 0.0
    assert runner._mean([]) is None
    assert runner._mean([None, 1.0, 3.0]) == 2.0
    with pytest.raises(ValueError, match="unknown policy"):
        runner.run_suite(src.build_all_scenarios()[:1], ["unrecognized"])


def test_reliability_rows_are_grounded_in_recorded_probability_snapshots(
    comparative_results,
) -> None:
    rows = runner.reliability_rows(comparative_results)
    expected_count = sum(len(result.probability_rows) for result in comparative_results)
    assert len(rows) == expected_count
    assert all(0.0 <= row["truth_probability"] <= 1.0 for row in rows)
    assert all(
        row["bin"]
        in {
            "0.0-0.2",
            "0.2-0.4",
            "0.4-0.6",
            "0.6-0.8",
            "0.8-1.0",
        }
        for row in rows
    )


def test_comparison_of_no_results_does_not_fabricate_successes() -> None:
    report = runner.aggregate([])
    for policy in ("single", "multi"):
        assert report[policy]["scenarios"] == 0
        assert report[policy]["accuracy"] is None
        assert report[policy]["brier_score"] is None
        assert report[policy]["mean_latency_ms_per_decision"] is None
    assert report["comparison"]["accuracy_delta"] is None
    assert report["comparison"]["brier_delta"] is None
    assert report["comparison"]["token_percent_change"] is None
    assert runner.render_markdown_table(report, []).count("n/a") > 1


@pytest.mark.parametrize("quiet", [False, True])
def test_cli_materializes_full_evidence_without_writing_outside_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    quiet: bool,
) -> None:
    output_dir = tmp_path / "reports"
    cases_output = tmp_path / "cases" / "scenarios.jsonl"
    argv = [
        "run_suite.py",
        "--output-dir",
        str(output_dir),
        "--cases-output",
        str(cases_output),
    ] + (["--quiet"] if quiet else [])
    monkeypatch.setattr(sys, "argv", argv)
    assert runner.main() == 0
    results_file = output_dir / "results.json"
    markdown_file = output_dir / "RESULTS.md"
    assert results_file.is_file() and markdown_file.is_file()
    payload = json.loads(results_file.read_text())
    assert payload["scenario_count"] == len(src.build_all_scenarios())
    assert payload["policies"] == ["single", "multi"]
    assert payload["token_model"]["tokens_per_branch_step"] == runner.TOKENS_PER_BRANCH_STEP
    assert len(payload["per_scenario"]) == 2 * payload["scenario_count"]
    assert payload["summary"]["multi"]["accuracy"] == 1.0
    assert cases_output.exists()
    cases = [json.loads(line) for line in cases_output.read_text().splitlines()]
    assert len(cases) == payload["scenario_count"]
    assert "Falsification benchmark results" in markdown_file.read_text()
    printed = capsys.readouterr().out
    if quiet:
        assert not printed
    else:
        assert "Aggregate summary" in printed
        assert "wrote" in printed
