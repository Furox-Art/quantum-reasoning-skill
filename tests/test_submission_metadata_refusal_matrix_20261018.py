"""Untrusted community benchmark metadata has no implicit or guessable defaults.

The public test workflow uses the Python standard-library unittest runner;
these assertions are deliberately independent of pytest and external plugins.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from quantum_reasoning_skill.benchmark import validate_submission as subject


def metadata():
    def conditions(label):
        return {
        "instruction_config": label, "sampling": {}, "tool_availability": [],
        "context_limit": 1000, "output_limit": 100,
    }
    return {
        "provider": "auditable", "model": "model", "run_date": "2026-10-18",
        "skill_version": "1.1.5", "repetitions_per_case": 1,
        "failures_recorded": True,
        "baseline": conditions("baseline"), "skill": conditions("skill"),
    }


class SubmissionMetadataRefusalTests(unittest.TestCase):
    def test_reference_metadata_is_valid(self):
        subject.validate_metadata(metadata())

    def test_root_requires_json_object(self):
        for value in (None, [], 1, "not-object"):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "JSON object"):
                subject.validate_metadata(value)

    def test_every_required_metadata_field_is_checked(self):
        for field in sorted(subject.META_FIELDS):
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, "missing fields"):
                doc = metadata()
                doc.pop(field)
                subject.validate_metadata(doc)

    def test_identity_fields_are_nonempty_strings(self):
        for name in ("provider", "model", "skill_version"):
            for value in ("", " ", None, 0, False, []):
                with self.subTest(name=name, value=value), self.assertRaisesRegex(ValueError, "non-empty string"):
                    doc = metadata()
                    doc[name] = value
                    subject.validate_metadata(doc)

    def test_date_is_strict_iso_date(self):
        for value in (0, None, [], 1, "yesterday", "2026-13-18"):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "run_date"):
                doc = metadata()
                doc["run_date"] = value
                subject.validate_metadata(doc)
        subject.validate_metadata(metadata())

    def test_repetition_is_positive_integer_not_boolean(self):
        for value in (False, True, 0, -1, 1.0, None, "1"):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "repetitions_per_case"):
                doc = metadata()
                doc["repetitions_per_case"] = value
                subject.validate_metadata(doc)

    def test_failures_recorded_requires_literal_true(self):
        for value in (False, None, 1, "true", {}):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "failures_recorded"):
                doc = metadata()
                doc["failures_recorded"] = value
                subject.validate_metadata(doc)

    def test_both_comparison_settings_must_be_objects(self):
        for side in ("baseline", "skill"):
            for value in (None, [], True, "instructions"):
                with self.subTest(side=side, value=value), self.assertRaisesRegex(ValueError, "must be an object"):
                    doc = metadata()
                    doc[side] = value
                    subject.validate_metadata(doc)

    def test_each_comparison_field_is_required(self):
        for side in ("baseline", "skill"):
            for field in sorted(subject.COND_FIELDS):
                with self.subTest(side=side, field=field), self.assertRaisesRegex(ValueError, "missing fields"):
                    doc = metadata()
                    doc[side].pop(field)
                    subject.validate_metadata(doc)

    def test_instruction_config_cannot_be_blank_or_coerced(self):
        for side in ("baseline", "skill"):
            for value in ("", " ", None, False, 5):
                with self.subTest(side=side, value=value), self.assertRaisesRegex(ValueError, "instruction_config"):
                    doc = metadata()
                    doc[side]["instruction_config"] = value
                    subject.validate_metadata(doc)

    def test_sampling_is_explicit_object(self):
        for side in ("baseline", "skill"):
            for value in (None, [], "temperature=0", False):
                with self.subTest(side=side, value=value), self.assertRaisesRegex(ValueError, "sampling"):
                    doc = metadata()
                    doc[side]["sampling"] = value
                    subject.validate_metadata(doc)

    def test_resource_limits_are_null_or_positive_integer(self):
        for side in ("baseline", "skill"):
            for field in ("context_limit", "output_limit"):
                for value in (True, False, 0, -1, 0.5, "100"):
                    with self.subTest(side=side, field=field, value=value), self.assertRaisesRegex(ValueError, field):
                        doc = metadata()
                        doc[side][field] = value
                        subject.validate_metadata(doc)

    def test_null_limits_are_explicitly_valid(self):
        doc = metadata()
        for side in ("baseline", "skill"):
            doc[side]["context_limit"] = None
            doc[side]["output_limit"] = None
        subject.validate_metadata(doc)

    def test_invalid_json_document_cannot_be_loaded(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "metadata.json"
            path.write_text("{broken:json", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "invalid JSON"):
                subject.load_json(path)

    def test_missing_document_reports_read_failure(self):
        with tempfile.TemporaryDirectory() as temp:
            missing = Path(temp) / "not-here.json"
            with self.assertRaisesRegex(ValueError, "unreadable|no such input file"):
                subject.load_json(missing)
            with self.assertRaisesRegex(ValueError, "unreadable|no such input file"):
                subject.load_text(missing)

    def test_missing_community_root_requires_explicit_allow_empty(self):
        with tempfile.TemporaryDirectory() as temp:
            missing = Path(temp) / "absent"
            with self.assertRaisesRegex(SystemExit, "community benchmark root not found"):
                subject.main(["--root", str(missing)])
            self.assertEqual(subject.main(["--root", str(missing), "--allow-empty"]), 0)
            with self.assertRaisesRegex(SystemExit, "no community benchmark bundles"):
                subject.main(["--root", temp])
            self.assertEqual(subject.main(["--root", temp, "--allow-empty"]), 0)

    def test_unreadable_community_root_is_not_accepted(self):
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp)
            real = Path.iterdir

            def unreadable(path):
                if path == target:
                    raise PermissionError("not accessible")
                return real(path)

            with patch.object(Path, "iterdir", unreadable), self.assertRaisesRegex(SystemExit, "not readable"):
                subject.main(["--root", str(target)])

    def test_duplicate_case_identifier_is_refused(self):
        with patch.object(subject.evaluate, "validate_case", return_value=None), self.assertRaisesRegex(ValueError, "duplicate case id"):
            subject._case_map([{"id": "same"}, {"id": "same"}])


if __name__ == "__main__":
    unittest.main()
