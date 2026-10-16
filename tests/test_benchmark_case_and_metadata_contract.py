"""Reproducible benchmark cases and run dates must satisfy published schemas."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from benchmark.evaluate import validate_case
from benchmark.validate_submission import validate_bundle, validate_metadata
from tests.test_submission_validation import SubmissionValidationTests


def _case() -> dict:
    return {
        "id": "case-1",
        "domain": "physics",
        "prompt": "Compute x.",
        "accepted_answers": ["42"],
    }


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("id", True), ("id", 1), ("id", "  "),
        ("domain", False), ("domain", 4), ("domain", ""),
        ("prompt", []), ("prompt", None), ("prompt", "\t"),
    ],
)
def test_required_case_strings_cannot_be_coerced(field: str, value: object) -> None:
    with pytest.raises(ValueError, match="must be a non-empty string"):
        validate_case({**_case(), field: value})


@pytest.mark.parametrize("answers", [[0], [True], [None], [""], [" "], ["42", False]])
def test_accepted_answers_must_be_nonempty_text(answers: list) -> None:
    with pytest.raises(ValueError, match="accepted_answers items"):
        validate_case({**_case(), "accepted_answers": answers})


def test_valid_text_case_remains_supported() -> None:
    validate_case(_case())
    validate_case({**_case(), "accepted_answers": ["42", " 42 "]})


@pytest.mark.parametrize(
    "run_date",
    [
        "20261017",
        "2026-W42-6",
        "2026-02-30",
        "2026-13-01",
        "2026-10-17T12:00",
        "2026/10/17",
        " 2026-10-17",
    ],
)
def test_metadata_rejects_noncanonical_or_impossible_dates(
    tmp_path: Path, run_date: str
) -> None:
    bundle = SubmissionValidationTests().make_bundle(tmp_path)
    meta = json.loads((bundle / "metadata.json").read_text(encoding="utf-8"))
    meta["run_date"] = run_date
    with pytest.raises(ValueError, match="metadata.run_date must be YYYY-MM-DD"):
        validate_metadata(meta)


def test_metadata_accepts_only_real_iso_calendar_dates(tmp_path: Path) -> None:
    bundle = SubmissionValidationTests().make_bundle(tmp_path)
    metadata = json.loads((bundle / "metadata.json").read_text(encoding="utf-8"))
    metadata["run_date"] = "2024-02-29"
    validate_metadata(metadata)
    metadata["run_date"] = "2023-02-29"
    with pytest.raises(ValueError, match="YYYY-MM-DD"):
        validate_metadata(metadata)


def test_bundle_file_date_validation_fails_before_scoring(tmp_path: Path) -> None:
    bundle = SubmissionValidationTests().make_bundle(tmp_path)
    path = bundle / "metadata.json"
    metadata = json.loads(path.read_text(encoding="utf-8"))
    metadata["run_date"] = "20261017"
    path.write_text(json.dumps(metadata), encoding="utf-8")
    with pytest.raises(ValueError, match="metadata.run_date"):
        validate_bundle(bundle)


def test_machine_schemas_agree_with_runtime_case_and_date_rules() -> None:
    root = Path(__file__).resolve().parents[1] / "benchmark" / "schemas"
    case_schema = json.loads((root / "case.schema.json").read_text(encoding="utf-8"))
    assert case_schema["properties"]["accepted_answers"]["items"] == {
        "type": "string", "minLength": 1, "pattern": r"\S"
    }
    metadata_schema = json.loads((root / "metadata.schema.json").read_text(encoding="utf-8"))
    assert metadata_schema["properties"]["run_date"]["pattern"] == r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$"
