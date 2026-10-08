"""Unit tests for the falsification benchmark runner.

These tests pin the deterministic behaviour of the suite: scenario inventory,
policy semantics, metric definitions and aggregate computation. They contain no
network or LLM calls and run in milliseconds.
"""

from __future__ import annotations

import importlib.util
import json
import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SUITE_DIR = REPO_ROOT / "benchmark" / "falsification"
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


runner = _load("falsification_run_suite", SUITE_DIR / "run_suite.py")
scenarios_mod = _load("falsification_scenarios", SUITE_DIR / "scenarios.py")


ALL_SCENARIOS = scenarios_mod.build_all_scenarios()


class ScenarioInventoryTests(unittest.TestCase):
    def test_scenario_types_are_present_and_deterministic(self):
        types = [s.scenario_type for s in ALL_SCENARIOS]
        self.assertIn("falsification", types)
        self.assertIn("revival", types)
        self.assertIn("control", types)
        self.assertEqual(len(ALL_SCENARIOS), 9)
        self.assertEqual(len({s.id for s in ALL_SCENARIOS}), 9)

    def test_every_scenario_has_ground_truth_and_steps(self):
        for scenario in ALL_SCENARIOS:
            self.assertTrue(scenario.steps, scenario.id)
            self.assertIn(scenario.truth_branch, scenario.steps[-1].metrics, scenario.id)
            self.assertTrue(scenario.accepted_answers, scenario.id)

    def test_metrics_are_in_range(self):
        for scenario in ALL_SCENARIOS:
            for step in scenario.steps:
                for branch_id, snapshot in step.metrics.items():
                    for name, value in snapshot.items():
                        self.assertTrue(
                            0.0 <= value <= 1.0,
                            f"{scenario.id} step {step.step} {branch_id}.{name}={value}",
                        )

    def test_falsification_scenarios_declare_decoy_and_falsification_step(self):
        for scenario in ALL_SCENARIOS:
            if scenario.scenario_type != "falsification":
                continue
            self.assertIsNotNone(scenario.decoy_branch, scenario.id)
            self.assertIsNotNone(scenario.falsified_at_step, scenario.id)
            falsification_step = next(
                s for s in scenario.steps if s.step == scenario.falsified_at_step
            )
            self.assertGreaterEqual(
                falsification_step.metrics[scenario.decoy_branch]["contradiction"],
                0.85,
                scenario.id,
            )

    def test_revival_scenarios_declare_revival_target(self):
        for scenario in ALL_SCENARIOS:
            if scenario.scenario_type != "revival":
                continue
            self.assertIsNotNone(scenario.revival_step, scenario.id)
            self.assertIsNotNone(scenario.revived_branch, scenario.id)

    def test_case_records_round_trip(self):
        record = scenarios_mod.scenario_as_case_record(ALL_SCENARIOS[0])
        self.assertEqual(
            set(record) >= {"id", "domain", "prompt", "accepted_answers"}, True
        )
        encoded = json.loads(json.dumps(record))
        self.assertEqual(encoded["id"], ALL_SCENARIOS[0].id)


class PolicyTests(unittest.TestCase):
    def test_single_policy_never_revisits_first_leader(self):
        scenario = next(s for s in ALL_SCENARIOS if s.scenario_type == "falsification")
        result = runner._run_single_policy(scenario)
        leaders = {step.leader for step in result.steps}
        self.assertEqual(len(leaders), 1, leaders)
        self.assertEqual(result.final_answer, result.steps[0].leader)

    def test_single_policy_fails_falsification_scenarios(self):
        for scenario in ALL_SCENARIOS:
            if scenario.scenario_type != "falsification":
                continue
            result = runner._run_single_policy(scenario)
            self.assertFalse(result.correct, scenario.id)
            self.assertFalse(result.switch_success, scenario.id)

    def test_multi_policy_solves_every_scenario(self):
        for scenario in ALL_SCENARIOS:
            result = runner._run_multi_policy(scenario)
            self.assertTrue(result.correct, f"{scenario.id} -> {result.final_answer}")

    def test_multi_policy_abandons_decoy_within_window(self):
        for scenario in ALL_SCENARIOS:
            if scenario.scenario_type != "falsification":
                continue
            result = runner._run_multi_policy(scenario)
            self.assertTrue(result.switch_success, scenario.id)
            self.assertIsNotNone(result.switch_delay_steps, scenario.id)
            self.assertLessEqual(result.switch_delay_steps, runner.SWITCH_WINDOW)

    def test_multi_policy_revives_required_branch(self):
        for scenario in ALL_SCENARIOS:
            if scenario.scenario_type != "revival":
                continue
            result = runner._run_multi_policy(scenario)
            self.assertTrue(result.revival_success, scenario.id)
            self.assertTrue(result.correct, scenario.id)

    def test_both_policies_solve_control_scenarios(self):
        for scenario in ALL_SCENARIOS:
            if scenario.scenario_type != "control":
                continue
            self.assertTrue(runner._run_single_policy(scenario).correct, scenario.id)
            self.assertTrue(runner._run_multi_policy(scenario).correct, scenario.id)

    def test_multi_policy_costs_more_tokens_than_single(self):
        results = runner.run_suite(ALL_SCENARIOS)
        multi = [r for r in results if r.policy == "multi"]
        single = [r for r in results if r.policy == "single"]
        self.assertGreater(
            sum(r.total_tokens for r in multi),
            sum(r.total_tokens for r in single),
        )


class MetricTests(unittest.TestCase):
    def test_brier_perfect_prediction_is_zero(self):
        rows = [
            {"step": 1, "scenario_id": "s", "truth": "H_A", "probabilities": {"H_A": 1.0}},
        ]
        self.assertEqual(runner._brier_from_rows(rows), 0.0)

    def test_brier_confident_wrong_is_near_two(self):
        rows = [
            {"step": 1, "scenario_id": "s", "truth": "H_A", "probabilities": {"H_A": 0.0}},
        ]
        self.assertAlmostEqual(runner._brier_from_rows(rows), 1.0)

    def test_brier_uniform_three_branches(self):
        rows = [
            {
                "step": 1,
                "scenario_id": "s",
                "truth": "H_A",
                "probabilities": {"H_A": 1 / 3, "H_B": 1 / 3, "H_C": 1 / 3},
            },
        ]
        expected = ((1 / 3 - 1) ** 2 + 2 * (1 / 3) ** 2) / 3
        self.assertAlmostEqual(runner._brier_from_rows(rows), expected)

    def test_softmax_is_deterministic_and_sums_to_one(self):
        scores = {"H_A": 0.8, "H_B": 0.4, "H_C": 0.1}
        first = runner._softmax_scores(scores)
        second = runner._softmax_scores(scores)
        self.assertEqual(first, second)
        self.assertAlmostEqual(sum(first.values()), 1.0)
        self.assertGreater(first["H_A"], first["H_C"])


class AggregateTests(unittest.TestCase):
    def setUp(self):
        self.results = runner.run_suite(ALL_SCENARIOS)
        self.summary = runner.aggregate(self.results)

    def test_aggregate_counts_all_runs(self):
        self.assertEqual(self.summary["single"]["scenarios"], 9)
        self.assertEqual(self.summary["multi"]["scenarios"], 9)

    def test_aggregate_reports_expected_headline_numbers(self):
        self.assertAlmostEqual(self.summary["single"]["accuracy"], 2 / 9)
        self.assertAlmostEqual(self.summary["multi"]["accuracy"], 1.0)
        self.assertAlmostEqual(
            self.summary["single"]["falsification"]["decision_switch_success_rate"], 0.0
        )
        self.assertAlmostEqual(
            self.summary["multi"]["falsification"]["decision_switch_success_rate"], 1.0
        )
        self.assertAlmostEqual(self.summary["multi"]["revival"]["revival_success_rate"], 1.0)

    def test_comparison_deltas_are_consistent(self):
        comparison = self.summary["comparison"]
        self.assertAlmostEqual(comparison["accuracy_delta"], 1.0 - 2 / 9)
        self.assertAlmostEqual(comparison["decision_switch_success_delta"], 1.0)
        self.assertIsNotNone(comparison["token_percent_change"])
        self.assertGreater(comparison["token_percent_change"], 0.0)

    def test_reliability_rows_reference_every_committed_step(self):
        rows = runner.reliability_rows(self.results)
        committed = sum(
            1
            for result in self.results
            for step in result.steps
            if step.answer_committed
        )
        self.assertEqual(len(rows), committed)
        for row in rows:
            self.assertTrue(row["bin"])
            self.assertTrue(0.0 <= row["truth_probability"] <= 1.0)


class ArtifactTests(unittest.TestCase):
    def test_scenarios_jsonl_matches_suite(self):
        path = SUITE_DIR / "scenarios.jsonl"
        self.assertTrue(path.exists(), "run run_suite.py to generate artifacts")
        rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
        self.assertEqual(len(rows), len(ALL_SCENARIOS))
        self.assertEqual(
            [row["id"] for row in rows], [s.id for s in ALL_SCENARIOS]
        )

    def test_results_json_matches_fresh_run(self):
        path = SUITE_DIR / "results" / "results.json"
        self.assertTrue(path.exists(), "run run_suite.py to generate artifacts")
        stored = json.loads(path.read_text(encoding="utf-8"))
        fresh = runner.aggregate(runner.run_suite(ALL_SCENARIOS))
        # Latency is wall-clock and legitimately varies between runs, so compare
        # every deterministic field and the accuracy-critical subset.
        self.assertEqual(stored["scenario_count"], 9)
        self.assertEqual(stored["summary"]["single"]["accuracy"], fresh["single"]["accuracy"])
        self.assertEqual(stored["summary"]["multi"]["accuracy"], fresh["multi"]["accuracy"])
        self.assertEqual(
            stored["summary"]["multi"]["falsification"]["decision_switch_success_rate"],
            fresh["multi"]["falsification"]["decision_switch_success_rate"],
        )
        self.assertEqual(
            stored["per_scenario"][0]["final_answer"],
            fresh and runner.run_suite([ALL_SCENARIOS[0]], policies=("single",))[0].final_answer,
        )


if __name__ == "__main__":
    unittest.main()
