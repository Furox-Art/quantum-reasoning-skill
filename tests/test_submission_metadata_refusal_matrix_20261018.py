"""Community benchmark submission checks must reject incomplete and tampered metadata."""

from __future__ import annotations

from pathlib import Path

import pytest

from benchmark import validate_submission as subject


def _metadata():
    return {
        "provider": "auditable", "model": "model", "run_date": "2026-10-18",
        "skill_version": "1.1.5", "repetitions_per_case": 1,
        "failures_recorded": True,
        "baseline": {
            "instruction_config": "baseline", "sampling": {}, "tool_availability": [],
            "context_limit": 1000, "output_limit": 100,
        },
        "skill": {
            "instruction_config": "skill", "sampling": {}, "tool_availability": [],
            "context_limit": 1000, "output_limit": 100,
        },
    }


def test_full_documented_metadata_is_accepted():
    subject.validate_metadata(_metadata())


@pytest.mark.parametrize("root", [None, [], 1, "not-object"])
def test_metadata_root_must_be_json_object(root):
    with pytest.raises(ValueError, match="JSON object"):
        subject.validate_metadata(root)


@pytest.mark.parametrize("missing", sorted(subject.META_FIELDS))
def test_every_required_metadata_field_is_checked(missing):
    meta = _metadata()
    meta.pop(missing)
    with pytest.raises(ValueError, match="missing fields"):
        subject.validate_metadata(meta)


@pytest.mark.parametrize("name", ["provider", "model", "skill_version"])
@pytest.mark.parametrize("value", ["", " ", None, 0, False, []])
def test_identifiers_must_be_nonempty_strings(name, value):
    meta = _metadata()
    meta[name] = value
    with pytest.raises(ValueError, match="non-empty string"):
        subject.validate_metadata(meta)


@pytest.mark.parametrize("value", [0, None, [], 1, "2026-10-18", "yesterday", "2026-13-18"])
def test_dates_must_be_valid_iso_date_strings(value):
    meta = _metadata()
    meta["run_date"] = value
    if value == "2026-10-18":
        subject.validate_metadata(meta)
    else:
        with pytest.raises(ValueError, match="run_date"):
            subject.validate_metadata(meta)


@pytest.mark.parametrize("value", [False, True, 0, -1, 1.0, None, "1"])
def test_repetitions_are_positive_integer_not_boolean(value):
    meta = _metadata()
    meta["repetitions_per_case"] = value
    with pytest.raises(ValueError, match="repetitions_per_case"):
        subject.validate_metadata(meta)


@pytest.mark.parametrize("value", [False, None, 1, "true", {}])
def test_failures_must_be_explicitly_recorded(value):
    meta = _metadata()
    meta["failures_recorded"] = value
    with pytest.raises(ValueError, match="failures_recorded"):
        subject.validate_metadata(meta)


@pytest.mark.parametrize("side", ["baseline", "skill"])
@pytest.mark.parametrize("value", [None, [], True, "instructions"])
def test_comparison_config_must_be_an_object(side, value):
    meta = _metadata()
    meta[side] = value
    with pytest.raises(ValueError, match=f"metadata.{side} must be an object"):
        subject.validate_metadata(meta)


@pytest.mark.parametrize("side", ["baseline", "skill"])
@pytest.mark.parametrize("field", sorted(subject.COND_FIELDS))
def test_each_comparison_config_field_is_required(side, field):
    meta = _metadata()
    meta[side].pop(field)
    with pytest.raises(ValueError, match="missing fields"):
        subject.validate_metadata(meta)


@pytest.mark.parametrize("side", ["baseline", "skill"])
@pytest.mark.parametrize("value", ["", " ", None, False, 5])
def test_instruction_config_must_be_a_nonempty_string(side, value):
    meta = _metadata()
    meta[side]["instruction_config"] = value
    with pytest.raises(ValueError, match="instruction_config"):
        subject.validate_metadata(meta)


@pytest.mark.parametrize("side", ["baseline", "skill"])
@pytest.mark.parametrize("value", [None, [], "temperature=0", False])
def test_sampling_config_must_be_an_object(side, value):
    meta = _metadata()
    meta[side]["sampling"] = value
    with pytest.raises(ValueError, match="sampling"):
        subject.validate_metadata(meta)


@pytest.mark.parametrize("side", ["baseline", "skill"])
@pytest.mark.parametrize("field", ["context_limit", "output_limit"])
@pytest.mark.parametrize("value", [True, False, 0, -1, 0.5, "100"])
def test_resource_limits_are_null_or_positive_integer(side, field, value):
    meta = _metadata()
    meta[side][field] = value
    with pytest.raises(ValueError, match=field):
        subject.validate_metadata(meta)


def test_null_resource_limits_are_explicitly_accepted():
    meta = _metadata()
    for side in ("baseline", "skill"):
        meta[side]["context_limit"] = None
        meta[side]["output_limit"] = None
    subject.validate_metadata(meta)


def test_invalid_json_document_cannot_be_loaded(tmp_path):
    file = tmp_path / "metadata.json"
    file.write_text("{broken:json", encoding="utf-8")
    with pytest.raises(ValueError, match="invalid JSON"):
        subject.load_json(file)


def test_unreadable_json_document_fails_explicitly(tmp_path):
    with pytest.raises(ValueError, match="unreadable"):
        subject.load_json(tmp_path / "missing.json")


def test_unreadable_readme_fails_explicitly(tmp_path):
    with pytest.raises(ValueError, match="unreadable"):
        subject.load_text(tmp_path / "missing.md")


def test_main_refuses_nonexistent_community_root(tmp_path):
    with pytest.raises(SystemExit, match="community benchmark root not found"):
        subject.main(["--root", str(tmp_path / "absent")])


def test_main_allows_explicitly_empty_community_root(tmp_path):
    assert subject.main(["--root", str(tmp_path / "absent"), "--allow-empty"]) == 0
    with pytest.raises(SystemExit, match="no community benchmark bundles"):
        subject.main(["--root", str(tmp_path)])
    assert subject.main(["--root", str(tmp_path), "--allow-empty"]) == 0


def test_main_refuses_unreadable_community_root(monkeypatch, tmp_path):
    original = Path.iterdir
    def fail(self):
        if self == tmp_path:
            raise PermissionError("isolated read denial")
        return original(self)
    monkeypatch.setattr(Path, "iterdir", fail)
    with pytest.raises(SystemExit, match="not readable"):
        subject.main(["--root", str(tmp_path)])


def test_duplicate_case_id_is_refused(monkeypatch):
    monkeypatch.setattr(subject.evaluate, "validate_case", lambda value: None)
    with pytest.raises(ValueError, match="duplicate case id"):
        subject._case_map([{"id": "same"}, {"id": "same"}])
