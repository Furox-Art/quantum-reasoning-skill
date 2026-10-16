"""Prevent misleading fractional counts and type-spoofed benchmark summaries."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from benchmark.evaluate import validate_result
from benchmark.validate_submission import _same_json_value, validate_bundle
from tests.test_submission_validation import SubmissionValidationTests


COUNT_FIELDS = (
    "tokens",
    "tool_calls",
    "branches_total",
    "branches_distinct",
    "revived_branches",
    "recovered_errors",
    "contradictions_found",
    "contradictions_resolved",
)


def _result(**changes: object) -> dict[str, object]:
    row: dict[str, object] = {
        "case_id": "case-1",
        "answer": "42",
        "tokens": 7,
        "tool_calls": 0,
        "latency_ms": 2.5,
        "branches_total": 1,
        "branches_distinct": 1,
        "revived_branches": 0,
        "recovered_errors": 0,
        "contradictions_found": 0,
        "contradictions_resolved": 0,
    }
    row.update(changes)
    return row


@pytest.mark.parametrize("name", COUNT_FIELDS)
@pytest.mark.parametrize("value", [1.5, 0.0, 1.0, True, -1, "2", None])
def test_count_telemetry_requires_a_nonnegative_integer(name: str, value: object) -> None:
    with pytest.raises(ValueError, match="finite and non-negative integer"):
        validate_result(_result(**{name: value}))


def test_count_telemetry_rejects_integer_too_large_for_a_finite_summary() -> None:
    with pytest.raises(ValueError, match="finite and non-negative integer"):
        validate_result(_result(tokens=10**1000))


def test_valid_integer_counts_and_fractional_latency_are_preserved() -> None:
    validate_result(_result(tokens=0, tool_calls=3, latency_ms=2.75))


@pytest.mark.parametrize(
    ("actual", "expected"),
    [
        (True, 1),
        (False, 0),
        (1, 1.0),
        (0.0, 0),
        ({"items": [True]}, {"items": [1]}),
        ({"summary": {"ratio": 1}}, {"summary": {"ratio": 1.0}}),
    ],
)
def test_comparison_requires_exact_json_types(actual: object, expected: object) -> None:
    assert actual == expected
    assert not _same_json_value(actual, expected)


def test_valid_comparison_with_nested_null_float_and_int_matches() -> None:
    values = {"skill": {"accuracy": 1.0, "cases_evaluated": 1, "missing": []}}
    assert _same_json_value(values, json.loads(json.dumps(values)))


@pytest.mark.parametrize("replacement", [True, 1.0])
def test_boolean_or_float_count_spoof_cannot_pass_bundle_verification(
    tmp_path: Path, replacement: object
) -> None:
    bundle = SubmissionValidationTests().make_bundle(tmp_path)
    path = bundle / "comparison.json"
    contents = json.loads(path.read_text(encoding="utf-8"))
    contents["skill"]["cases_evaluated"] = replacement
    path.write_text(json.dumps(contents), encoding="utf-8")
    with pytest.raises(ValueError, match="comparison.json does not match"):
        validate_bundle(bundle)


def test_valid_bundle_remains_accepted(tmp_path: Path) -> None:
    bundle = SubmissionValidationTests().make_bundle(tmp_path)
    validate_bundle(bundle)


def test_published_schema_declares_discrete_counters_as_integers() -> None:
    from pathlib import Path

    path = Path(__file__).resolve().parents[1] / "benchmark" / "schemas" / "result.schema.json"
    schema = json.loads(path.read_text(encoding="utf-8"))
    for field in COUNT_FIELDS:
        assert schema["properties"][field]["type"] == "integer"
        assert schema["properties"][field]["minimum"] == 0
    assert schema["properties"]["latency_ms"]["type"] == "number"
