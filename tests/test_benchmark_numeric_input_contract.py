"""Benchmark results must not silently certify non-finite measurements."""

from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from benchmark.evaluate import read_jsonl, strict_json_loads, validate_result
from benchmark.validate_submission import load_json


def result(**changes: object) -> dict[str, object]:
    record: dict[str, object] = {
        "case_id": "case-1",
        "answer": "42",
        "tokens": 20,
        "tool_calls": 1,
        "latency_ms": 100.0,
    }
    record.update(changes)
    return record


@pytest.mark.parametrize("metric", ["tokens", "tool_calls", "latency_ms"])
@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf, 10**1000])
def test_required_telemetry_rejects_nonfinite_or_unrepresentable_numbers(
    metric: str, value: float | int
) -> None:
    with pytest.raises(ValueError, match="finite and non-negative"):
        validate_result(result(**{metric: value}))


@pytest.mark.parametrize(
    "metric",
    [
        "branches_total",
        "branches_distinct",
        "revived_branches",
        "recovered_errors",
        "contradictions_found",
        "contradictions_resolved",
    ],
)
@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf, 10**1000])
def test_optional_telemetry_rejects_invalid_numbers(metric: str, value: float | int) -> None:
    with pytest.raises(ValueError, match="finite and non-negative"):
        validate_result(result(**{metric: value}))


@pytest.mark.parametrize(
    "source",
    [
        '{"case_id":"a","case_id":"b"}',
        '{"nested":{"answer":"a","answer":"b"}}',
        '{"answer":NaN}',
        '{"answer":Infinity}',
        '{"answer":1e9999}',
    ],
)
def test_ambiguous_json_never_parses(source: str) -> None:
    with pytest.raises(ValueError):
        strict_json_loads(source)


def test_jsonl_duplicate_key_reports_precise_line(tmp_path: Path) -> None:
    source = tmp_path / "results.jsonl"
    source.write_text(
        '{"case_id":"c1","answer":"ok","tokens":1,"tool_calls":0,"latency_ms":2}\n'
        '{"case_id":"c2","case_id":"c1","answer":"bad","tokens":1,"tool_calls":0,"latency_ms":2}\n',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match=r"results\.jsonl:2: invalid JSON: duplicate"):
        read_jsonl(source)


@pytest.mark.parametrize("source", ['{"field":NaN}', '{"field":1e9999}', '{"field":1,"field":2}'])
def test_submission_metadata_rejects_ambiguous_json(tmp_path: Path, source: str) -> None:
    path = tmp_path / "metadata.json"
    path.write_text(source, encoding="utf-8")
    with pytest.raises(ValueError, match="invalid JSON"):
        load_json(path)


def test_normal_benchmark_json_remains_compatible() -> None:
    record = result()
    validate_result(record)
    assert strict_json_loads(json.dumps(record)) == record
