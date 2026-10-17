"""Adversarial community-submission validation with reproducible real bundles."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from benchmark import evaluate
from benchmark import validate_submission as validator
from tests.test_submission_validation import SubmissionValidationTests


def _bundle(tmp_path: Path) -> Path:
    return SubmissionValidationTests().make_bundle(tmp_path)


def _metadata(tmp_path: Path) -> tuple[Path, dict]:
    root = _bundle(tmp_path)
    return root, json.loads((root / "metadata.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize(
    ("field", "bad"),
    [
        ("provider", 1),
        ("provider", "  "),
        ("model", None),
        ("model", ""),
        ("skill_version", False),
        ("skill_version", ""),
        ("repetitions_per_case", 0),
        ("repetitions_per_case", True),
        ("repetitions_per_case", -2),
        ("failures_recorded", 1),
        ("run_date", "2026-02-30"),
        ("run_date", "20261017"),
    ],
)
def test_metadata_rejects_invalid_top_level_values(
    tmp_path: Path,
    field: str,
    bad: object,
) -> None:
    _, metadata = _metadata(tmp_path)
    metadata[field] = bad
    with pytest.raises(ValueError):
        validator.validate_metadata(metadata)


@pytest.mark.parametrize(
    ("condition", "field", "bad"),
    [
        ("baseline", "instruction_config", ""),
        ("skill", "instruction_config", False),
        ("baseline", "sampling", []),
        ("skill", "sampling", "nonsense"),
        ("baseline", "context_limit", True),
        ("baseline", "context_limit", 0),
        ("skill", "context_limit", -2),
        ("baseline", "output_limit", "100"),
        ("skill", "output_limit", 0),
        ("skill", "output_limit", False),
    ],
)
def test_condition_metadata_rejects_ambiguous_or_wrong_type(
    tmp_path: Path,
    condition: str,
    field: str,
    bad: object,
) -> None:
    _, metadata = _metadata(tmp_path)
    metadata[condition][field] = bad
    with pytest.raises(ValueError):
        validator.validate_metadata(metadata)


@pytest.mark.parametrize("bad", [None, True, [], "text", 12])
def test_metadata_root_is_only_object(bad: object) -> None:
    with pytest.raises(ValueError, match="metadata.json must contain"):
        validator.validate_metadata(bad)


@pytest.mark.parametrize("field", ["baseline", "skill"])
def test_metadata_requires_complete_condition_contract(
    tmp_path: Path,
    field: str,
) -> None:
    _, meta = _metadata(tmp_path)
    invalid = copy.deepcopy(meta)
    invalid[field] = None
    with pytest.raises(ValueError, match="must be an object"):
        validator.validate_metadata(invalid)
    del meta[field]["tool_availability"]
    with pytest.raises(ValueError, match="missing fields"):
        validator.validate_metadata(meta)


def test_metadata_missing_top_level_key_is_refused(tmp_path: Path) -> None:
    _, metadata = _metadata(tmp_path)
    del metadata["provider"]
    with pytest.raises(ValueError, match="missing fields"):
        validator.validate_metadata(metadata)


def test_valid_null_limits_preserved(tmp_path: Path) -> None:
    _, meta = _metadata(tmp_path)
    meta["baseline"]["context_limit"] = None
    meta["skill"]["output_limit"] = None
    validator.validate_metadata(meta)


@pytest.mark.parametrize(
    ("left", "right", "expected"),
    [
        (True, 1, False),
        (1, 1.0, False),
        ({"a": True}, {"a": 1}, False),
        ([1, {"a": True}], [1, {"a": True}], True),
        ([1], [1, 2], False),
        ({"a": 1}, {"a": 1, "b": 2}, False),
        ({"a": [1, 2]}, {"a": [1, 3]}, False),
        (None, None, True),
    ],
)
def test_recursive_json_comparison_never_coerces_types(left, right, expected) -> None:
    assert validator._same_json_value(left, right) is expected


def test_case_mapping_refuses_duplicates() -> None:
    case = {"id": "x", "domain": "math", "prompt": "1+1?", "accepted_answers": ["2"]}
    with pytest.raises(ValueError, match="duplicate case id"):
        validator._case_map([case, copy.deepcopy(case)])


@pytest.mark.parametrize(
    ("member", "data", "message"),
    [
        ("README.md", "", "README.md must not be empty"),
        ("baseline.jsonl", '{"case_id":"absent","answer":"2","tokens":1,"tool_calls":0,"latency_ms":1}\n', "must contain exactly one row"),
        ("skill.jsonl", '{"case_id":"absent","answer":"2","tokens":1,"tool_calls":0,"latency_ms":1}\n', "must contain exactly one row"),
        ("metadata.json", "{}", "missing fields"),
        ("comparison.json", '{"wrong":1}', "does not match"),
    ],
)
def test_bundle_rejects_missing_or_forged_reproducibility_artifacts(
    tmp_path: Path,
    member: str,
    data: str,
    message: str,
) -> None:
    root = _bundle(tmp_path)
    (root / member).write_text(data, encoding="utf-8")
    with pytest.raises(ValueError, match=message):
        validator.validate_bundle(root)


def test_bundle_rejects_duplicate_case_ids(tmp_path: Path) -> None:
    root = _bundle(tmp_path)
    path = root / "cases.jsonl"
    path.write_text(path.read_text() * 2)
    with pytest.raises(ValueError, match="duplicate case id"):
        validator.validate_bundle(root)


@pytest.mark.parametrize("row_name", ["baseline.jsonl", "skill.jsonl"])
def test_bundle_rejects_duplicate_score_rows(tmp_path: Path, row_name: str) -> None:
    root = _bundle(tmp_path)
    path = root / row_name
    path.write_text(path.read_text() * 2)
    with pytest.raises(ValueError, match="duplicate"):
        validator.validate_bundle(root)


def test_symlinked_member_escaping_bundle_is_rejected(tmp_path: Path) -> None:
    root = _bundle(tmp_path)
    outside = tmp_path / "outside"
    outside.write_text('{"comparison": {}}')
    (root / "comparison.json").unlink()
    (root / "comparison.json").symlink_to(outside)
    with pytest.raises(ValueError, match="bundle|outside"):
        validator.validate_bundle(root)


def test_load_json_refuses_read_errors_and_parser_ambiguity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "payload.json"
    path.write_text('{"valid":1,"valid":2}')
    with pytest.raises(ValueError, match="invalid JSON"):
        validator.load_json(path)
    with pytest.raises(ValueError, match="invalid JSON"):
        path.write_text('{"invalid":')
        validator.load_json(path)

    def unreadable(*args, **kwargs):
        raise OSError("permission denied")

    monkeypatch.setattr(evaluate, "read_text_limited", unreadable)
    with pytest.raises(ValueError, match="unreadable"):
        validator.load_json(path)
    with pytest.raises(ValueError, match="unreadable"):
        validator.load_text(path)


def test_oversize_json_and_readme_are_refused(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "payload.txt"
    path.write_text("1234567890")
    with pytest.raises(ValueError):
        validator.load_json(path, max_bytes=4)
    with pytest.raises(ValueError):
        validator.load_text(path, max_bytes=4)


@pytest.mark.parametrize(
    ("allow_empty", "root_exists", "expected"),
    [
        (True, False, 0),
        (False, False, "error"),
        (True, True, 0),
        (False, True, "error"),
    ],
)
def test_validator_cli_never_invents_missing_community_bundles(
    tmp_path: Path,
    allow_empty: bool,
    root_exists: bool,
    expected: object,
) -> None:
    root = tmp_path / "community"
    if root_exists:
        root.mkdir()
    args = ["--root", str(root)]
    if allow_empty:
        args.append("--allow-empty")
    if expected == "error":
        with pytest.raises(SystemExit):
            validator.main(args)
    else:
        assert validator.main(args) == 0


def test_validator_cli_accepts_recomputed_valid_bundle(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    root = tmp_path / "community"
    root.mkdir()
    _bundle(root)
    assert validator.main(["--root", str(root)]) == 0
    assert "validated" in capsys.readouterr().out
