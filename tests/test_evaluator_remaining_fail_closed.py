"""Previously uncovered evaluator error, CLI and serialization paths."""

from __future__ import annotations

import json
import runpy
import sys
from pathlib import Path

import pytest

from benchmark import evaluate as ev
from benchmark import validate_submission as validator


CASE = {"id": "c1", "domain": "math", "prompt": "1 + 1", "accepted_answers": ["2"]}
RESULT = {"case_id": "c1", "answer": "2", "tokens": 1, "tool_calls": 0, "latency_ms": 1.0}


@pytest.mark.parametrize(
    "data",
    [
        {},
        {"id": "c1", "domain": "math", "prompt": "x"},
        {"id": "", "domain": "math", "prompt": "x", "accepted_answers": ["x"]},
        {"id": "c1", "domain": "math", "prompt": "", "accepted_answers": ["x"]},
        {"id": "c1", "domain": "math", "prompt": "x", "accepted_answers": []},
        {"id": "c1", "domain": "math", "prompt": "x", "accepted_answers": [False]},
    ],
)
def test_case_validator_refuses_missing_and_malformed_fields(data) -> None:
    with pytest.raises(ValueError):
        ev.validate_case(data)


def test_evaluator_rejects_invalid_cases_and_results() -> None:
    with pytest.raises(ValueError, match="case must be"):
        ev.validate_case("not a case")
    with pytest.raises(ValueError, match="result must be"):
        ev.validate_result([])
    with pytest.raises(ValueError, match="must be unique"):
        ev.summarize([CASE, dict(CASE)], [RESULT])
    with pytest.raises(ValueError, match="duplicate result"):
        ev.summarize([CASE], [RESULT, dict(RESULT)])
    with pytest.raises(ValueError, match="finite and non-negative"):
        ev.validate_result({**RESULT, "latency_ms": 1e309})


def test_evaluator_aggregate_preserves_missingness_without_invented_success() -> None:
    empty = ev.summarize([CASE], [])
    assert empty["cases_evaluated"] == 0
    assert empty["accuracy"] is None
    assert empty["mean_tokens"] is None
    assert empty["missing_case_ids"] == ["c1"]
    assert ev.safe_mean([]) is None
    assert ev.safe_ratio(2, 0) is None
    assert ev.absolute_change(None, 1) is None
    assert ev.absolute_change(1, None) is None
    assert ev.percent_change(None, 1) is None
    assert ev.percent_change(1, None) is None
    assert ev.percent_change(1, 0) is None
    assert ev.percent_change(3, 2) == pytest.approx(50)
    assert ev.absolute_change(3, 2) == 1


def test_read_jsonl_blank_entries_and_invalid_lines_keep_line_number(tmp_path: Path) -> None:
    path = tmp_path / "rows.jsonl"
    path.write_text("\n \n" + json.dumps(CASE) + "\n")
    assert ev.read_jsonl(path) == [CASE]
    path.write_text(' \n{"a":1,"a":2}\n')
    with pytest.raises(ValueError, match=":2: invalid JSON"):
        ev.read_jsonl(path)
    path.write_text("[]\n")
    with pytest.raises(ValueError, match="row must be a JSON object"):
        ev.read_jsonl(path)


def test_file_validation_catches_missing_and_oversized_inputs(tmp_path: Path) -> None:
    with pytest.raises(ev.MissingInputError):
        ev.read_text_limited(tmp_path / "absent", 100)
    path = tmp_path / "payload"
    path.write_text("abc")
    with pytest.raises(ev.UnsafeJsonError):
        ev.read_text_limited(path, 1)
    assert ev.read_text_limited(path, 3) == "abc"


def test_large_count_overflow_does_not_crash_or_round(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    huge = 10**500
    assert not ev._valid_count(huge)
    with pytest.raises(ValueError):
        ev.validate_result({**RESULT, "tokens": huge})
    with pytest.raises(ValueError):
        ev.validate_result({**RESULT, "latency_ms": huge})


def test_recursive_numeric_guard_rejects_nan_before_output() -> None:
    with pytest.raises(ValueError, match="is not finite"):
        ev.ensure_finite(float("inf"), "accuracy")
    with pytest.raises(ValueError, match="is not finite"):
        ev.ensure_finite(float("nan"), "accuracy")
    ev.ensure_finite(1.0, "accuracy")


def test_cli_rejects_bad_byte_limit_without_touching_sources(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as exc:
        ev.main(["--max-bytes", "0", "--skill", "absent"])
    assert exc.value.code == 2
    assert "must be positive" in capsys.readouterr().err


def test_cli_output_is_fenced_to_user_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "cases.jsonl").write_text(json.dumps(CASE) + "\n")
    (tmp_path / "results.jsonl").write_text(json.dumps(RESULT) + "\n")
    argv = [
        "--cases-dir",
        str(tmp_path),
        "--cases",
        "cases.jsonl",
        "--skill",
        "results.jsonl",
        "--baseline",
        "results.jsonl",
        "--output",
        "derived/metrics.json",
    ]
    assert ev.main(argv) == 0
    results = json.loads((tmp_path / "derived/metrics.json").read_text())
    assert results["comparison"]["accuracy_delta"] == 0.0
    assert "comparison" in capsys.readouterr().out


def test_cli_missing_case_file_reports_typed_error_not_traceback(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert ev.main(["--cases-dir", str(tmp_path), "--cases", "absent", "--skill", "absent"]) == 2
    assert "results file" in capsys.readouterr().err.lower()


def test_direct_script_main_guards_operate_without_writing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sys, "argv", ["evaluate.py", "--skill", "not-real"])
    with pytest.raises(SystemExit) as exc:
        runpy.run_module("benchmark.evaluate", run_name="__main__")
    assert exc.value.code == 2
    monkeypatch.setattr(
        sys, "argv", ["validate_submission.py", "--root", "/no/community/root", "--allow-empty"]
    )
    with pytest.raises(SystemExit) as exc:
        runpy.run_module("benchmark.validate_submission", run_name="__main__")
    assert exc.value.code == 0


def test_oversized_comparison_bundle_text_propagates_typed_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "large-readme"
    path.write_text("a" * 100)
    with pytest.raises(ValueError, match="exceeds"):
        validator.load_text(path, max_bytes=2)


def test_symlinked_untrusted_input_cannot_escape_cases_dir(
    tmp_path: Path,
) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "rows.jsonl").write_text(json.dumps(CASE) + "\n")
    sandbox = tmp_path / "sandbox"
    sandbox.mkdir()
    (sandbox / "link").symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError):
        ev.read_jsonl(sandbox / "link" / "rows.jsonl", base=sandbox)
