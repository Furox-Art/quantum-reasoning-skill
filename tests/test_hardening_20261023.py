"""Round-2 hardening: terminal rejection, real revival, and a bounded switch clock."""

from __future__ import annotations

import dataclasses
import unittest

from quantum_reasoning_skill.benchmark.falsification import run_suite as runner
from quantum_reasoning_skill.benchmark.falsification import scenarios
from quantum_reasoning_skill.reference import branch_controller as bc


def _snapshot(**overrides):
    values = {
        "evidence": 0.8,
        "verification": 0.7,
        "independence": 0.9,
        "information_gain": 0.5,
        "contradiction": 0.05,
        "unresolved_assumptions": 0.1,
        "normalized_cost": 0.1,
        "shared_assumption_ratio": 0.0,
        "semantic_similarity_to_leader": 0.0,
    }
    values.update(overrides)
    return values


def _scenario(steps, **overrides):
    values = {
        "id": "hardening-case",
        "scenario_type": "control",
        "domain": "test",
        "prompt": "A deterministic branch decision?",
        "truth_branch": "H_B",
        "answer": "H_B",
        "accepted_answers": ["H_B"],
        "decoy_branch": None,
        "falsified_at_step": None,
        "revival_step": None,
        "revived_branch": None,
        "steps": steps,
        "notes": "synthetic hardening case",
    }
    values.update(overrides)
    return scenarios.Scenario(**values)


def _weak_target(**overrides):
    values = {
        "evidence": 0.15,
        "verification": 0.05,
        "independence": 0.70,
        "information_gain": 0.50,
        "contradiction": 0.30,
        "unresolved_assumptions": 0.85,
        "normalized_cost": 0.20,
    }
    values.update(overrides)
    return _snapshot(**values)


class TerminalRejectionTests(unittest.TestCase):
    def test_rejected_branch_stays_rejected_under_classify_and_update(self):
        branch = bc.Branch(
            "H_C",
            bc.BranchMetrics(**_snapshot(contradiction=0.0)),
            state=bc.BranchState.REJECTED,
        )
        self.assertEqual(bc.classify_branch(branch).state, bc.BranchState.REJECTED)
        self.assertEqual(bc.update_branch_state(branch).state, bc.BranchState.REJECTED)

    def test_material_improvement_does_not_revive_a_rejected_branch(self):
        previous = bc.BranchMetrics(**_weak_target())
        current = bc.BranchMetrics(**_snapshot(evidence=0.95, verification=0.95))
        branch = bc.Branch(
            "H_C",
            current,
            state=bc.BranchState.REJECTED,
            previous_metrics=previous,
        )
        self.assertFalse(bc.should_revive(branch))
        self.assertEqual(bc.update_branch_state(branch).state, bc.BranchState.REJECTED)

    def test_rejected_branch_is_not_silently_reopened_by_later_evidence(self):
        sample = next(
            scenario
            for scenario in scenarios.build_revival_scenarios()
            if scenario.id == "revival-003"
        )
        changed = dataclasses.replace(sample, revived_branch=None, revival_step=None)
        result = runner._run_multi_policy(changed)
        by_step = {step.step: step for step in result.steps}
        self.assertEqual(by_step[2].branch_states["H_C"], "rejected")
        self.assertEqual(by_step[3].branch_states["H_C"], "rejected")
        self.assertNotIn("H_C", by_step[3].revived_this_step)
        self.assertFalse(result.correct)

    def test_explicit_reopen_is_the_documented_path_from_rejection(self):
        sample = next(
            scenario
            for scenario in scenarios.build_revival_scenarios()
            if scenario.id == "revival-003"
        )
        result = runner._run_multi_policy(sample)
        by_step = {step.step: step for step in result.steps}
        self.assertEqual(by_step[2].branch_states["H_C"], "rejected")
        self.assertEqual(by_step[3].branch_states["H_C"], "active")
        self.assertIn("H_C", by_step[3].revived_this_step)
        self.assertTrue(result.revival_success)


class RevivalTransitionTests(unittest.TestCase):
    def _dormant_scenario(self, step_two_evidence: float) -> scenarios.Scenario:
        steps = [
            scenarios.EvidenceStep(
                1,
                {"H_A": _snapshot(evidence=0.95), "H_B": _weak_target()},
                answer_known_from=True,
            ),
            scenarios.EvidenceStep(
                2,
                {
                    "H_A": _snapshot(evidence=0.95),
                    "H_B": _weak_target(evidence=step_two_evidence),
                },
                answer_known_from=True,
            ),
        ]
        return _scenario(
            steps,
            scenario_type="revival",
            revival_step=2,
            revived_branch="H_B",
        )

    def test_dormant_branch_without_material_change_is_not_a_revival(self):
        result = runner._run_multi_policy(self._dormant_scenario(0.16))
        by_step = {step.step: step for step in result.steps}
        self.assertEqual(by_step[1].branch_states["H_B"], "dormant")
        self.assertEqual(by_step[2].branch_states["H_B"], "dormant")
        self.assertFalse(result.revival_success)

    def test_material_change_transitions_dormant_to_active(self):
        result = runner._run_multi_policy(self._dormant_scenario(0.40))
        by_step = {step.step: step for step in result.steps}
        self.assertEqual(by_step[1].branch_states["H_B"], "dormant")
        self.assertEqual(by_step[2].branch_states["H_B"], "active")
        self.assertIn("H_B", by_step[2].revived_this_step)
        self.assertTrue(result.revival_success)

    def test_results_serialize_per_step_branch_states(self):
        result = runner._run_multi_policy(self._dormant_scenario(0.40))
        row = runner.results_to_dicts([result])[0]
        self.assertEqual(row["steps"][1]["branch_states"]["H_B"], "active")


class SwitchClockTests(unittest.TestCase):
    def test_earlier_truth_lead_does_not_produce_a_negative_delay(self):
        steps = [
            scenarios.EvidenceStep(
                1,
                {"H_A": _snapshot(evidence=0.30, contradiction=0.05), "H_B": _snapshot()},
                answer_known_from=True,
            ),
            scenarios.EvidenceStep(
                2,
                {"H_A": _snapshot(evidence=0.10, contradiction=0.95), "H_B": _snapshot()},
                answer_known_from=True,
            ),
        ]
        result = runner._run_multi_policy(
            _scenario(
                steps,
                scenario_type="falsification",
                decoy_branch="H_A",
                falsified_at_step=2,
            )
        )
        self.assertTrue(result.switch_success)
        self.assertEqual(result.switch_delay_steps, 0)

    def test_switch_beyond_the_window_fails_and_reports_no_delay(self):
        steps = [
            scenarios.EvidenceStep(
                1,
                {"H_A": _snapshot(evidence=0.90, contradiction=0.50), "H_B": _weak_target()},
                answer_known_from=True,
            ),
            scenarios.EvidenceStep(
                2,
                {"H_A": _snapshot(evidence=0.90, contradiction=0.50), "H_B": _weak_target()},
                answer_known_from=True,
            ),
            scenarios.EvidenceStep(
                3,
                {"H_A": _snapshot(evidence=0.20, contradiction=0.60), "H_B": _snapshot()},
                answer_known_from=True,
            ),
        ]
        result = runner._run_multi_policy(
            _scenario(
                steps,
                scenario_type="falsification",
                decoy_branch="H_A",
                falsified_at_step=1,
            )
        )
        self.assertFalse(result.switch_success)
        self.assertIsNone(result.switch_delay_steps)

    def test_declared_step_is_the_fallback_when_metrics_never_cross(self):
        steps = [
            scenarios.EvidenceStep(
                1,
                {"H_A": _snapshot(contradiction=0.10), "H_B": _snapshot()},
                answer_known_from=True,
            )
        ]
        declared = _scenario(
            steps,
            scenario_type="falsification",
            decoy_branch="H_A",
            falsified_at_step=1,
        )
        self.assertEqual(runner._falsification_step(declared), 1)
        result = runner._run_single_policy(declared)
        self.assertTrue(result.switch_success)
        self.assertEqual(result.switch_delay_steps, 0)

    def test_decoy_without_a_falsification_event_leaves_the_metric_unset(self):
        steps = [
            scenarios.EvidenceStep(
                1, {"H_A": _snapshot(), "H_B": _snapshot(evidence=0.95)}
            )
        ]
        result = runner._run_single_policy(
            _scenario(steps, scenario_type="falsification", decoy_branch="H_A")
        )
        self.assertIsNone(result.switch_success)
        self.assertIsNone(result.switch_delay_steps)

    def test_falsification_step_ignores_steps_without_the_decoy(self):
        steps = [
            scenarios.EvidenceStep(1, {"H_B": _snapshot()}),
            scenarios.EvidenceStep(
                2, {"H_A": _snapshot(contradiction=0.90), "H_B": _snapshot()}
            ),
        ]
        scenario = _scenario(steps, decoy_branch="H_A")
        self.assertEqual(runner._falsification_step(scenario), 2)

    def test_aggregate_delay_mean_only_covers_successful_switches(self):
        sample = scenarios.build_falsification_scenarios()[0]
        success = runner._run_multi_policy(sample)
        failure = dataclasses.replace(
            success, switch_success=False, switch_delay_steps=None
        )
        summary = runner.aggregate([success, failure])
        self.assertEqual(
            summary["multi"]["falsification"]["mean_switch_delay_steps"],
            success.switch_delay_steps,
        )
        self.assertEqual(
            summary["multi"]["falsification"]["decision_switch_success_rate"], 0.5
        )


if __name__ == "__main__":
    unittest.main()
