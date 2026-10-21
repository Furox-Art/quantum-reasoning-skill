"""Deterministic falsification report, serialization and CLI artifact contracts."""

from __future__ import annotations

import json
import math
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from quantum_reasoning_skill.benchmark.falsification import run_suite as subject
from quantum_reasoning_skill.benchmark.falsification.scenarios import (
    build_all_scenarios,
)


class FalsificationArtifactTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scenarios = build_all_scenarios()
        cls.results = subject.run_suite(cls.scenarios)
        cls.summary = subject.aggregate(cls.results)

    def test_all_scenarios_have_two_policy_results(self):
        self.assertEqual(len(self.results), 2 * len(self.scenarios))
        self.assertEqual({r.policy for r in self.results}, {"single", "multi"})
        self.assertEqual({r.scenario_id for r in self.results}, {s.id for s in self.scenarios})

    def test_unknown_policy_refused(self):
        with self.assertRaisesRegex(ValueError, "unknown policy"):
            subject.run_suite(self.scenarios[:1], policies=["not a policy"])

    def test_no_requested_policies_gives_empty_results(self):
        self.assertEqual(subject.run_suite(self.scenarios[:1], policies=[]), [])

    def test_softmax_empty_tie_and_preferred_evidence(self):
        self.assertEqual(subject._softmax_scores({}), {})
        self.assertEqual(subject._softmax_scores({"b": 0.5, "a": 0.5}), {"a": 0.5, "b": 0.5})
        probability = subject._softmax_scores({"first": 0.9, "second": 0.2})
        self.assertLessEqual(abs(sum(probability.values()) - 1.0), 1e-12)
        self.assertGreater(probability["first"], probability["second"])

    def test_comparison_metrics_have_explicit_bounded_values(self):
        self.assertIn("comparison", self.summary)
        for policy in ("single", "multi"):
            with self.subTest(policy=policy):
                block = self.summary[policy]
                self.assertEqual(block["scenarios"], len(self.scenarios))
                self.assertGreaterEqual(block["accuracy"], 0)
                self.assertLessEqual(block["accuracy"], 1)
                self.assertTrue(math.isfinite(block["total_latency_ms"]))

    def test_reliability_probability_buckets(self):
        rows = subject.reliability_rows(self.results)
        self.assertTrue(rows)
        bins = {"0.0-0.2", "0.2-0.4", "0.4-0.6", "0.6-0.8", "0.8-1.0"}
        for row in rows:
            self.assertIn(row["bin"], bins)
            self.assertGreaterEqual(row["truth_probability"], 0)
            self.assertLessEqual(row["truth_probability"], 1)

    def test_serialized_evidence_is_json_and_complete(self):
        rows = subject.results_to_dicts(self.results)
        self.assertEqual(len(rows), len(self.results))
        self.assertEqual(json.loads(json.dumps(rows, allow_nan=False)), rows)
        for item in rows:
            with self.subTest(scenario=item["scenario_id"], policy=item["policy"]):
                self.assertIn("final_answer", item)
                self.assertIn("truth", item)
                self.assertIn("switch_success", item)
                self.assertIn("revival_success", item)
                self.assertEqual(item["total_tokens"], sum(step["tokens"] for step in item["steps"]))

    def test_markdown_contains_all_scenarios_and_calibration(self):
        report = subject.render_markdown_table(self.summary, self.results)
        self.assertIn("## Aggregate summary", report)
        self.assertIn("## Per-scenario results", report)
        self.assertIn("Brier score", report)
        for scenario in self.scenarios:
            self.assertIn(scenario.id, report)

    def test_missing_switch_and_revival_are_reported_as_na(self):
        step = subject.StepRecord(1, "a", 0.5, {"a": 1.0}, True, True, 1, 0, 0)
        result = subject.ScenarioResult("synthetic", "control", "single", "a", "a", True, [step], 0, 0.0, 0.0, None, None, 0, None, None)
        self.assertEqual(subject._switch_text(result), "n/a")
        self.assertEqual(subject._revival_text(result), "n/a")
        self.assertIsNone(subject.results_to_dicts([result])[0]["brier"])
        self.assertIn("n/a", subject.render_markdown_table(self.summary, [result]))

    def test_formatted_success_and_failure_switch_and_revival(self):
        for result in self.results:
            if result.switch_success is True:
                self.assertTrue(subject._switch_text(result).startswith("yes (+"))
            elif result.switch_success is False:
                self.assertEqual(subject._switch_text(result), "no")
            if result.revival_success is True:
                self.assertEqual(subject._revival_text(result), "yes")
            elif result.revival_success is False:
                self.assertEqual(subject._revival_text(result), "no")

    def test_full_cli_creates_isolated_json_markdown_and_cases(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            output = root / "reports"
            cases = root / "replay" / "cases.jsonl"
            with patch.object(sys, "argv", ["runner.py", "--output-dir", str(output), "--cases-output", str(cases), "--quiet"]):
                self.assertEqual(subject.main(), 0)
            self.assertTrue((output / "RESULTS.md").is_file())
            self.assertTrue(cases.is_file())
            payload = json.loads((output / "results.json").read_text(encoding="utf-8"))
            self.assertEqual(payload["scenario_count"], len(self.scenarios))
            self.assertEqual(payload["policies"], ["single", "multi"])
            self.assertEqual(len(payload["per_scenario"]), len(self.results))
            self.assertEqual(len(cases.read_text().splitlines()), len(self.scenarios))
            for row in cases.read_text().splitlines():
                self.assertIn("accepted_answers", json.loads(row))

    def test_full_cli_prints_produced_paths_when_not_quiet(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            console = StringIO()
            with patch.object(sys, "argv", ["runner.py", "--output-dir", str(root / "results"), "--cases-output", str(root / "cases.jsonl")]), redirect_stdout(console):
                self.assertEqual(subject.main(), 0)
            self.assertIn("wrote ", console.getvalue())
            self.assertIn("## Per-scenario results", console.getvalue())


if __name__ == "__main__":
    unittest.main()
