"""Actual community bundle corruption, incomplete evidence and integrity gates."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from benchmark import evaluate, validate_submission as validator
from reference import branch_controller as bc


def make_bundle(root):
    bundle = root / "publisher"
    bundle.mkdir()
    cases = [{"id": "one", "domain": "reasoning", "prompt": "One?", "accepted_answers": ["one"]}]
    baseline = [{"case_id": "one", "answer": "one", "tokens": 3, "tool_calls": 0, "latency_ms": 4}]
    skill = [{"case_id": "one", "answer": "one", "tokens": 2, "tool_calls": 0, "latency_ms": 3}]
    for name, data in (("cases.jsonl", cases), ("baseline.jsonl", baseline), ("skill.jsonl", skill)):
        (bundle / name).write_text("".join(json.dumps(row) + "\n" for row in data))
    cond = {"instruction_config": "reference", "sampling": {}, "tool_availability": [], "context_limit": None, "output_limit": None}
    metadata = {"provider": "independent", "model": "reported", "run_date": "2026-10-18",
                "skill_version": "1.1.5", "repetitions_per_case": 1,
                "failures_recorded": True, "baseline": cond, "skill": cond}
    (bundle / "metadata.json").write_text(json.dumps(metadata))
    summary = {"baseline": evaluate.summarize(cases, baseline), "skill": evaluate.summarize(cases, skill)}
    summary["comparison"] = evaluate.compare(summary["baseline"], summary["skill"])
    (bundle / "comparison.json").write_text(json.dumps(summary))
    (bundle / "README.md").write_text("Independently reproducible results.\n")
    return bundle


class CommunityIntegrityAttackTests(unittest.TestCase):
    def test_complete_bundle_passes_actual_evaluator_comparison(self):
        with tempfile.TemporaryDirectory() as td:
            validator.validate_bundle(make_bundle(Path(td)))

    def test_missing_directory_is_not_an_empty_bundle(self):
        with tempfile.TemporaryDirectory() as td, self.assertRaisesRegex(ValueError, "unreadable bundle directory"):
            validator.validate_bundle(Path(td) / "not-created")

    def test_duplicate_baseline_and_skill_entries_are_refused(self):
        for name in ("baseline.jsonl", "skill.jsonl"):
            with tempfile.TemporaryDirectory() as td:
                bundle = make_bundle(Path(td))
                path = bundle / name
                raw = path.read_text()
                path.write_text(raw + raw)
                with self.subTest(file=name), self.assertRaisesRegex(ValueError, "duplicate"):
                    validator.validate_bundle(bundle)

    def test_missing_result_row_is_not_implicitly_assumed_correct(self):
        for name in ("baseline.jsonl", "skill.jsonl"):
            with tempfile.TemporaryDirectory() as td:
                bundle = make_bundle(Path(td))
                (bundle / name).write_text("")
                with self.subTest(file=name), self.assertRaisesRegex(ValueError, "exactly one row"):
                    validator.validate_bundle(bundle)

    def test_empty_readme_is_not_documentation_of_provenance(self):
        with tempfile.TemporaryDirectory() as td:
            bundle = make_bundle(Path(td))
            (bundle / "README.md").write_text("   ")
            with self.assertRaisesRegex(ValueError, "README.md must not be empty"):
                validator.validate_bundle(bundle)

    def test_oversized_json_and_readme_cannot_pass_byte_budget(self):
        with tempfile.TemporaryDirectory() as td:
            bundle = make_bundle(Path(td))
            for name, loader in (("metadata.json", validator.load_json), ("README.md", validator.load_text)):
                with self.subTest(file=name), self.assertRaisesRegex(ValueError, "exceeds"):
                    loader(bundle / name, max_bytes=1)

    def test_cli_prints_validated_bundle_only_after_full_integrity_pass(self):
        from contextlib import redirect_stdout
        from io import StringIO
        with tempfile.TemporaryDirectory() as td:
            bundle = make_bundle(Path(td))
            output = StringIO()
            with redirect_stdout(output):
                self.assertEqual(validator.main(["--root", td]), 0)
            self.assertIn("validated", output.getvalue())
            self.assertIn(bundle.name, output.getvalue())

    def test_invalid_comparison_record_is_not_accepted_after_other_valid_checks(self):
        with tempfile.TemporaryDirectory() as td:
            bundle = make_bundle(Path(td))
            content = json.loads((bundle / "comparison.json").read_text())
            content["comparison"]["accuracy_delta"] = 999
            (bundle / "comparison.json").write_text(json.dumps(content))
            with self.assertRaisesRegex(ValueError, "comparison.json does not match"):
                validator.validate_bundle(bundle)

    def test_non_object_jsonl_record_is_refused_with_line_number(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "record.jsonl"
            p.write_text("\n[]\n")
            with self.assertRaisesRegex(ValueError, "row must be a JSON object"):
                evaluate.read_jsonl(p)

    def test_blank_jsonl_lines_are_skipped_without_fabricating_records(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "record.jsonl"
            p.write_text("\n \n" + json.dumps({"id": "one"}) + "\n\n")
            self.assertEqual(evaluate.read_jsonl(p), [{"id": "one"}])

    def test_invalid_baseline_cli_path_is_typed_as_missing_input(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            case = root / "cases.jsonl"
            skill = root / "skill.jsonl"
            case.write_text(json.dumps({"id": "one", "domain": "reasoning", "prompt": "p", "accepted_answers": ["one"]}) + "\n")
            skill.write_text(json.dumps({"case_id": "one", "answer": "one", "tokens": 1, "tool_calls": 0, "latency_ms": 1}) + "\n")
            self.assertEqual(evaluate.main(["--cases", str(case), "--skill", str(skill),
                                           "--baseline", str(root / "unavailable.jsonl")]), evaluate.EXIT_MISSING_INPUT)

    def test_generic_near_tie_prevents_premature_branch_collapse(self):
        strong = bc.BranchMetrics(0.95, 0.98, 0.9, 0.1, 0, 0, 0)
        almost_strong = bc.BranchMetrics(0.94, 0.97, 0.9, 0.1, 0, 0, 0)
        thresholds = bc.Thresholds(collapse_score=0.1, collapse_verification=0.1,
                                   collapse_max_contradiction=1.0, collapse_margin=0.4)
        can, reason, _ = bc.collapse_decision(
            [bc.Branch("leader", strong), bc.Branch("alternative", almost_strong)], thresholds
        )
        self.assertFalse(can)
        self.assertIn("margin is too small", reason)

    def test_high_information_near_tie_is_reported_specifically(self):
        strong = bc.BranchMetrics(0.95, 0.98, 0.9, 0.75, 0, 0, 0)
        other = bc.BranchMetrics(0.94, 0.97, 0.9, 0.72, 0, 0, 0)
        thresholds = bc.Thresholds(collapse_score=0.1, collapse_verification=0.1,
                                   collapse_max_contradiction=1.0, collapse_margin=0.4,
                                   unresolved_near_leader_margin=0.4)
        can, reason, _ = bc.collapse_decision(
            [bc.Branch("leader", strong), bc.Branch("alternative", other)], thresholds
        )
        self.assertFalse(can)
        self.assertIn("high-information alternative", reason)


if __name__ == "__main__":
    unittest.main()
