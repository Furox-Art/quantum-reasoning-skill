from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "benchmark_evaluate", ROOT / "benchmark" / "evaluate.py"
)
assert SPEC and SPEC.loader
evaluate = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(evaluate)


CASES = [
    {
        "id": "c1",
        "domain": "math",
        "prompt": "1+1?",
        "accepted_answers": ["2"],
    },
    {
        "id": "c2",
        "domain": "logic",
        "prompt": "yes?",
        "accepted_answers": ["yes"],
    },
]


class BenchmarkTests(unittest.TestCase):
    def test_summary_computes_accuracy_and_telemetry(self):
        results = [
            {
                "case_id": "c1",
                "answer": "2",
                "tokens": 100,
                "tool_calls": 1,
                "latency_ms": 50,
                "branches_total": 4,
                "branches_distinct": 3,
                "revived_branches": 1,
                "recovered_errors": 1,
                "contradictions_found": 2,
                "contradictions_resolved": 2,
            },
            {
                "case_id": "c2",
                "answer": "no",
                "tokens": 200,
                "tool_calls": 3,
                "latency_ms": 150,
                "branches_total": 2,
                "branches_distinct": 1,
                "revived_branches": 0,
                "recovered_errors": 0,
                "contradictions_found": 1,
                "contradictions_resolved": 0,
            },
        ]
        summary = evaluate.summarize(CASES, results)
        self.assertEqual(summary["accuracy"], 0.5)
        self.assertEqual(summary["mean_tokens"], 150.0)
        self.assertEqual(summary["mean_tool_calls"], 2.0)
        self.assertEqual(summary["mean_latency_ms"], 100.0)
        self.assertEqual(summary["branch_diversity_ratio"], 4 / 6)
        self.assertEqual(summary["contradiction_resolution_rate"], 2 / 3)

    def test_compare_reports_cost_and_accuracy_changes(self):
        baseline = {
            "accuracy": 0.5,
            "mean_tokens": 100.0,
            "mean_tool_calls": 1.0,
            "mean_latency_ms": 100.0,
            "branch_diversity_ratio": 0.4,
            "contradiction_resolution_rate": 0.5,
        }
        skill = {
            "accuracy": 0.75,
            "mean_tokens": 150.0,
            "mean_tool_calls": 2.0,
            "mean_latency_ms": 120.0,
            "branch_diversity_ratio": 0.7,
            "contradiction_resolution_rate": 0.8,
        }
        delta = evaluate.compare(baseline, skill)
        self.assertEqual(delta["accuracy_delta"], 0.25)
        self.assertEqual(delta["tokens_percent_change"], 50.0)
        self.assertEqual(delta["tool_calls_percent_change"], 100.0)
        self.assertEqual(delta["latency_percent_change"], 20.0)
        self.assertAlmostEqual(delta["branch_diversity_delta"], 0.3)
        self.assertAlmostEqual(delta["contradiction_resolution_delta"], 0.3)

    def test_missing_result_fields_fail(self):
        with self.assertRaises(ValueError):
            evaluate.summarize(
                CASES,
                [{"case_id": "c1", "answer": "2", "tokens": 1}],
            )

    def test_unknown_case_id_fails(self):
        with self.assertRaises(ValueError):
            evaluate.summarize(
                CASES,
                [
                    {
                        "case_id": "missing",
                        "answer": "2",
                        "tokens": 1,
                        "tool_calls": 0,
                        "latency_ms": 1,
                    }
                ],
            )


if __name__ == "__main__":
    unittest.main()
