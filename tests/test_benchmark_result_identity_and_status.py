"""Case identity and execution outcome cannot be spoofed in benchmark metrics."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from benchmark.evaluate import summarize, validate_result
from benchmark.validate_submission import validate_bundle
from tests.test_submission_validation import SubmissionValidationTests


def _result(**changes: object) -> dict:
    row = {
        "case_id": "True",
        "answer": "2",
        "tokens": 5,
        "tool_calls": 0,
        "latency_ms": 12,
    }
    row.update(changes)
    return row


def _cases() -> list[dict]:
    return [{"id": "True", "domain": "math", "prompt": "1+1?", "accepted_answers": ["2"]}]


@pytest.mark.parametrize("case_id", [True, False, 1, 1.0, None, [], "", "  "])
def test_result_identity_requires_nonblank_string(case_id: object) -> None:
    with pytest.raises(ValueError, match="case_id must be a non-empty string"):
        validate_result(_result(case_id=case_id))


@pytest.mark.parametrize("status", ["timeout", "error", "refusal"])
def test_failed_runs_never_count_correct_despite_a_matching_answer(status: str) -> None:
    row = _result(status=status)
    result = summarize(_cases(), [row])
    assert result["cases_evaluated"] == 1
    assert result["accuracy"] == 0.0
    assert result["mean_tokens"] == 5.0


@pytest.mark.parametrize("status", ["ok", None])
def test_successful_or_legacy_missing_status_counts_real_answer(status: str | None) -> None:
    row = _result() if status is None else _result(status=status)
    assert summarize(_cases(), [row])["accuracy"] == 1.0


@pytest.mark.parametrize("status", ["SUCCESS", "", False, None, 1, []])
def test_invalid_outcome_status_is_refused(status: object) -> None:
    with pytest.raises(ValueError, match="invalid status"):
        validate_result(_result(status=status))


def test_bundle_with_forged_boolean_case_id_is_rejected(tmp_path: Path) -> None:
    bundle = SubmissionValidationTests().make_bundle(tmp_path)
    path = bundle / "skill.jsonl"
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    rows[0]["case_id"] = True
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n")
    with pytest.raises(ValueError, match="case_id must be"):
        validate_bundle(bundle)


def test_result_schema_declares_text_case_id_and_valid_statuses() -> None:
    schema_path = Path(__file__).resolve().parents[1] / "benchmark" / "schemas" / "result.schema.json"
    schema = json.loads(schema_path.read_text())
    assert schema["properties"]["case_id"]["type"] == "string"
    assert schema["properties"]["case_id"]["pattern"] == r"\S"
    assert set(schema["properties"]["status"]["enum"]) == {"ok", "refusal", "timeout", "error"}
