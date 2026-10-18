"""Real untrusted benchmark inputs, scientific telemetry and branch-control refusals."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from benchmark import evaluate
from reference import branch_controller as bc


def valid_case():
    return {"id": "sample", "domain": "reasoning", "prompt": "Which?", "accepted_answers": ["answer"]}


def valid_result():
    return {"case_id": "sample", "answer": "answer", "tokens": 2, "tool_calls": 0, "latency_ms": 3}


def metrics(**overrides):
    fields = {"evidence": 0.9, "verification": 0.95, "independence": 0.9,
              "information_gain": 0.5, "contradiction": 0.0,
              "unresolved_assumptions": 0.0, "normalized_cost": 0.0}
    fields.update(overrides)
    return bc.BranchMetrics(**fields)


class EvaluatorAdversarialContractTests(unittest.TestCase):
    def test_valid_case_and_result(self):
        evaluate.validate_case(valid_case())
        evaluate.validate_result(valid_result())

    def test_case_requires_json_object(self):
        for value in (None, [], 3, "sample"):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "JSON object"):
                evaluate.validate_case(value)

    def test_each_case_field_is_required(self):
        for field in ("id", "domain", "prompt", "accepted_answers"):
            item = valid_case()
            item.pop(field)
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, "missing"):
                evaluate.validate_case(item)

    def test_accepted_answers_are_nonempty_list(self):
        for value in (None, [], "yes", False):
            item = valid_case()
            item["accepted_answers"] = value
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "accepted_answers"):
                evaluate.validate_case(item)

    def test_results_require_json_object_and_all_fields(self):
        with self.assertRaisesRegex(ValueError, "JSON object"):
            evaluate.validate_result([])
        for field in valid_result():
            item = valid_result()
            item.pop(field)
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, "missing fields"):
                evaluate.validate_result(item)

    def test_primary_telemetry_rejects_boolean_negative_and_non_numeric(self):
        for field in ("tokens", "tool_calls", "latency_ms"):
            for value in (True, -1, None, "fast"):
                item = valid_result()
                item[field] = value
                with self.subTest(field=field, value=value), self.assertRaisesRegex(ValueError, "non-negative"):
                    evaluate.validate_result(item)

    def test_optional_telemetry_has_same_non_negative_contract(self):
        for field in evaluate.OPTIONAL_TELEMETRY_FIELDS:
            item = valid_result()
            item[field] = -2
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, "non-negative"):
                evaluate.validate_result(item)

    def test_branch_distinct_count_cannot_exceed_total(self):
        item = valid_result()
        item.update(branches_total=1, branches_distinct=2)
        with self.assertRaisesRegex(ValueError, "branches_distinct cannot exceed"):
            evaluate.validate_result(item)

    def test_resolved_contradictions_cannot_exceed_found(self):
        item = valid_result()
        item.update(contradictions_found=0, contradictions_resolved=2)
        with self.assertRaisesRegex(ValueError, "contradictions_resolved cannot exceed"):
            evaluate.validate_result(item)

    def test_summarize_rejects_duplicate_case_identifiers(self):
        with self.assertRaisesRegex(ValueError, "case ids must be unique"):
            evaluate.summarize([valid_case(), valid_case()], [valid_result()])

    def test_summarize_rejects_duplicate_and_unknown_result(self):
        with self.assertRaisesRegex(ValueError, "duplicate result"):
            evaluate.summarize([valid_case()], [valid_result(), valid_result()])
        item = valid_result()
        item["case_id"] = "unregistered"
        with self.assertRaisesRegex(ValueError, "unknown case_id"):
            evaluate.summarize([valid_case()], [item])

    def test_summarize_missing_result_is_reported_not_fabricated(self):
        result = evaluate.summarize([valid_case()], [])
        self.assertEqual(result["missing_case_ids"], ["sample"])
        self.assertIsNone(result["accuracy"])
        self.assertIsNone(result["mean_tokens"])

    def test_telemetry_statistics_are_grounded_in_actual_rows(self):
        row = valid_result()
        row.update(branches_total=4, branches_distinct=3,
                   contradictions_found=2, contradictions_resolved=1,
                   revived_branches=1, recovered_errors=2)
        out = evaluate.summarize([valid_case()], [row])
        self.assertEqual(out["accuracy"], 1.0)
        self.assertEqual(out["branch_diversity_ratio"], 0.75)
        self.assertEqual(out["contradiction_resolution_rate"], 0.5)
        self.assertEqual(out["revival_rate_per_case"], 1.0)
        self.assertEqual(out["error_recovery_rate_per_case"], 2.0)

    def test_finite_guard_refuses_nan_and_infinity(self):
        for value in (float("nan"), float("inf"), float("-inf")):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "not finite"):
                evaluate.ensure_finite(value, "scientific metric")
        evaluate.ensure_finite(3.0, "scientific metric")

    def test_missing_files_exit_with_explicit_missing_input_code(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self.assertEqual(evaluate.main(["--cases", str(root / "no-cases.jsonl"),
                                             "--skill", str(root / "no-results.jsonl")]),
                             evaluate.EXIT_MISSING_INPUT)

    def test_valid_replay_cli_writes_json_without_fabricated_results(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            cases = root / "cases.jsonl"
            results = root / "skill.jsonl"
            output = root / "report.json"
            cases.write_text(json.dumps(valid_case()) + "\n", encoding="utf-8")
            results.write_text(json.dumps(valid_result()) + "\n", encoding="utf-8")
            self.assertEqual(evaluate.main(["--cases", str(cases), "--skill", str(results),
                                            "--cases-dir", td, "--output", str(output)]), 0)
            payload = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(payload["skill"]["cases_evaluated"], 1)
            self.assertNotIn("comparison", payload)

    def test_replay_cli_refuses_invalid_maximum_size(self):
        with self.assertRaises(SystemExit):
            evaluate.main(["--max-bytes", "0", "--skill", "whatever.jsonl"])

    def test_read_jsonl_rejects_non_object_and_bad_json_lines(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "cases.jsonl"
            for content in ("[]\n", "{broken:json\n"):
                p.write_text(content, encoding="utf-8")
                with self.subTest(content=content), self.assertRaises(ValueError):
                    evaluate.read_jsonl(p)


class BranchStateBoundaryTests(unittest.TestCase):
    def test_invalid_branch_telemetry_is_refused_before_scoring(self):
        with self.assertRaisesRegex(ValueError, "in \\[0, 1\\]"):
            bc.branch_score(metrics(evidence=1.2))

    def test_entropy_nonfinite_and_negative_inputs_are_rejected(self):
        for value in (float("nan"), float("inf"), -0.01):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "finite and non-negative"):
                bc.normalized_entropy([0.5, value])

    def test_entropy_infinite_sum_is_refused(self):
        with self.assertRaisesRegex(ValueError, "total must be finite"):
            bc.normalized_entropy([1e308, 1e308])

    def test_entropy_empty_zero_and_single_branch(self):
        self.assertEqual(bc.normalized_entropy([]), 0.0)
        self.assertEqual(bc.normalized_entropy([0.0, 0.0]), 0.0)
        self.assertEqual(bc.normalized_entropy([0.0, 1.0]), 0.0)

    def test_width_bands_and_invalid_uncertainty(self):
        self.assertEqual(bc.recommended_width(0.1), (2, 3))
        self.assertEqual(bc.recommended_width(0.4), (4, 6))
        self.assertEqual(bc.recommended_width(0.9), (6, 10))
        for value in (-1, 2, float("nan")):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "uncertainty"):
                bc.recommended_width(value)

    def test_empty_or_low_scoring_branch_never_collapses(self):
        empty = bc.collapse_decision([])
        self.assertFalse(empty[0])
        low = bc.Branch("weak", metrics(evidence=0, verification=0, independence=0,
                                         information_gain=0, contradiction=1,
                                         unresolved_assumptions=1, normalized_cost=1))
        outcome = bc.collapse_decision([low])
        self.assertFalse(outcome[0])

    def test_diversity_refuses_out_of_range_similarity(self):
        self.assertEqual(bc.diversity_ratio([]), 1.0)
        with self.assertRaisesRegex(ValueError, "duplicate_threshold"):
            bc.diversity_ratio([0.2], duplicate_threshold=2)
        for value in (-0.1, 1.2):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "similarity values"):
                bc.diversity_ratio([value])

    def test_diversity_ratio_tracks_redundancy_not_branch_count(self):
        self.assertEqual(bc.diversity_ratio([0.1, 0.9], duplicate_threshold=0.85), 0.5)

    def test_rejected_branch_does_not_contribute_to_uncertainty(self):
        rejected = bc.Branch("excluded", metrics(), state=bc.BranchState.REJECTED)
        self.assertEqual(bc.uncertainty_from_branches([rejected]), 0.0)


if __name__ == "__main__":
    unittest.main()
