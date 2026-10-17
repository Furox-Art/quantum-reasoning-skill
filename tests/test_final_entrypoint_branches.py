"""Entrypoint and exceptional-flow proofs for reproducible benchmark execution."""

from __future__ import annotations

import builtins
import json
import runpy
import sys
from dataclasses import replace
from pathlib import Path

import pytest

from benchmark import evaluate as ev
from benchmark import validate_submission as validator
import benchmark
from benchmark.falsification import run_suite as runner
from benchmark.falsification import scenarios as src


CASE = {"id": "c1", "domain": "math", "prompt": "calculate", "accepted_answers": ["2"]}
RESULT = {"case_id": "c1", "answer": "2", "tokens": 1, "tool_calls": 1, "latency_ms": 1}


def test_package_root_and_integrity_raise_on_incomplete_package(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert benchmark.package_root().is_dir()
    monkeypatch.setattr(benchmark, "_EXPECTED_MODULES", ("missing_module_example.py",))
    with pytest.raises(ImportError, match="incomplete"):
        benchmark._verify_integrity()


def test_benchmark_both_relative_import_modes_load_same_project_sources(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = str(Path(__file__).resolve().parents[1])
    with monkeypatch.context() as ctx:
        ctx.setattr(sys, "path", [item for item in sys.path if item != root])
        loaded = runpy.run_path(
            str(Path(root) / "benchmark/falsification/run_suite.py"), run_name="loaded_directly"
        )
        assert "run_suite" in loaded
        assert root in sys.path

    imported = builtins.__import__
    calls = []

    def one_import_failure(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "benchmark" and fromlist and "evaluate" in fromlist and not calls:
            calls.append("forced_direct_script_fallback")
            raise ImportError("simulate running script without repo root")
        return imported(name, globals, locals, fromlist, level)

    with monkeypatch.context() as ctx:
        ctx.setattr(builtins, "__import__", one_import_failure)
        loaded = runpy.run_path(
            str(Path(root) / "benchmark/validate_submission.py"), run_name="loaded_directly"
        )
        assert loaded["load_json"] is not None
    assert calls == ["forced_direct_script_fallback"]


def test_community_directory_read_failure_reports_typed_cli_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    community = tmp_path / "community"
    community.mkdir()
    original = Path.iterdir

    def broken(self):
        if self == community:
            raise OSError("permission denied")
        return original(self)

    monkeypatch.setattr(Path, "iterdir", broken)
    with pytest.raises(ValueError, match="unreadable bundle"):
        validator.validate_bundle(community)
    with pytest.raises(SystemExit, match="root not readable"):
        validator.main(["--root", str(community)])


def test_evaluator_fails_invalid_telemetry_consistency_checks() -> None:
    with pytest.raises(ValueError, match="branches_distinct cannot exceed"):
        ev.validate_result(
            {
                **RESULT,
                "branches_total": 2,
                "branches_distinct": 3,
            }
        )
    with pytest.raises(ValueError, match="contradictions_resolved cannot exceed"):
        ev.validate_result(
            {
                **RESULT,
                "contradictions_found": 0,
                "contradictions_resolved": 1,
            }
        )


def test_evaluator_cli_valid_skill_without_comparison_or_output(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    (tmp_path / "cases.jsonl").write_text(json.dumps(CASE) + "\n")
    (tmp_path / "results.jsonl").write_text(json.dumps(RESULT) + "\n")
    assert (
        ev.main(
            [
                "--cases-dir",
                str(tmp_path),
                "--cases",
                "cases.jsonl",
                "--skill",
                "results.jsonl",
            ]
        )
        == 0
    )
    result = json.loads(capsys.readouterr().out)
    assert result["skill"]["accuracy"] == 1.0
    assert "comparison" not in result


def test_evaluator_cli_propagates_nondict_summaries_without_crash(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    (tmp_path / "cases.jsonl").write_text(json.dumps(CASE) + "\n")
    (tmp_path / "results.jsonl").write_text(json.dumps(RESULT) + "\n")
    monkeypatch.setattr(ev, "summarize", lambda cases, results: None)
    assert (
        ev.main(
            [
                "--cases-dir",
                str(tmp_path),
                "--cases",
                "cases.jsonl",
                "--skill",
                "results.jsonl",
            ]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out)["skill"] is None


def test_missing_revival_target_does_not_invent_a_revival() -> None:
    original = src.build_all_scenarios()[0]
    altered = replace(original, revived_branch="missing_branch", revival_step=1)
    result = runner._run_multi_policy(altered)
    assert result.revival_success is False


def test_collapse_outcome_is_exposed_for_verifiably_high_quality_branch() -> None:
    metrics = src._branch(1, 1, 1, 1, 0, 0, 0)
    scenario = replace(
        src.build_all_scenarios()[0],
        decoy_branch=None,
        truth_branch="correct",
        steps=[
            src.EvidenceStep(
                step=1,
                metrics={"correct": metrics},
                answer_known_from=True,
            )
        ],
    )
    result = runner._run_multi_policy(scenario)
    assert result.correct is True
    assert result.steps[0].collapsed
    assert result.steps[0].collapse_reason == "collapse criteria satisfied"


def test_falsification_suite_main_guard_writes_only_explicit_sandbox_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_suite.py",
            "--output-dir",
            str(tmp_path / "results"),
            "--cases-output",
            str(tmp_path / "cases.jsonl"),
            "--quiet",
        ],
    )
    with pytest.raises(SystemExit) as exit_code:
        runpy.run_module("benchmark.falsification.run_suite", run_name="__main__")
    assert exit_code.value.code == 0
    assert (tmp_path / "results/results.json").is_file()
    assert (tmp_path / "cases.jsonl").is_file()


def test_reporting_handles_integer_source_values_as_strings() -> None:
    results = runner.run_suite(src.build_all_scenarios())
    report = runner.aggregate(results)
    report["single"]["accuracy"] = 1
    table = runner.render_markdown_table(report, results)
    assert "| overall accuracy | 1 |" in table
