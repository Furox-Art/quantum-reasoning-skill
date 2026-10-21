from __future__ import annotations

from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import conftest  # noqa: E402  (repository root is on sys.path only after the insert)

assert_close = conftest.assert_close

from quantum_reasoning_skill.reference import branch_controller as bc  # noqa: E402


class BranchControllerTests(unittest.TestCase):
    def metrics(self, **overrides):
        values = {
            "evidence": 0.8,
            "verification": 0.8,
            "independence": 0.9,
            "information_gain": 0.6,
            "contradiction": 0.1,
            "unresolved_assumptions": 0.1,
            "normalized_cost": 0.2,
            "shared_assumption_ratio": 0.0,
            "semantic_similarity_to_leader": 0.0,
        }
        values.update(overrides)
        return bc.BranchMetrics(**values)

    def test_score_penalizes_shared_assumptions(self):
        independent = self.metrics(shared_assumption_ratio=0.0)
        correlated = self.metrics(shared_assumption_ratio=0.8)
        self.assertGreater(bc.branch_score(independent), bc.branch_score(correlated))

    def test_high_contradiction_rejects_branch(self):
        branch = bc.Branch("bad", self.metrics(contradiction=0.95))
        updated = bc.classify_branch(branch)
        self.assertEqual(updated.state, bc.BranchState.REJECTED)

    def test_material_evidence_change_revives_dormant_branch(self):
        previous = self.metrics(evidence=0.30, verification=0.35, contradiction=0.50)
        current = self.metrics(evidence=0.50, verification=0.35, contradiction=0.50)
        branch = bc.Branch(
            "revive",
            current,
            state=bc.BranchState.DORMANT,
            previous_metrics=previous,
        )
        self.assertTrue(bc.should_revive(branch))
        self.assertEqual(bc.update_branch_state(branch).state, bc.BranchState.ACTIVE)

    def test_collapse_requires_clear_verified_leader(self):
        leader = bc.Branch(
            "leader",
            self.metrics(
                evidence=1.0,
                verification=1.0,
                independence=1.0,
                information_gain=0.8,
                contradiction=0.0,
                unresolved_assumptions=0.0,
                normalized_cost=0.0,
            ),
        )
        weak = bc.Branch(
            "weak",
            self.metrics(
                evidence=0.35,
                verification=0.30,
                independence=0.5,
                information_gain=0.2,
                contradiction=0.4,
                unresolved_assumptions=0.5,
                normalized_cost=0.4,
            ),
        )
        can_collapse, reason, selected = bc.collapse_decision([leader, weak])
        self.assertTrue(can_collapse, reason)
        self.assertEqual(selected.branch_id, "leader")

    def test_close_competitor_blocks_collapse(self):
        first = bc.Branch(
            "a",
            self.metrics(
                evidence=1.0,
                verification=1.0,
                independence=1.0,
                information_gain=0.2,
                contradiction=0.0,
                unresolved_assumptions=0.0,
                normalized_cost=0.0,
            ),
        )
        second = bc.Branch(
            "b",
            self.metrics(
                evidence=0.95,
                verification=0.95,
                independence=1.0,
                information_gain=0.2,
                contradiction=0.0,
                unresolved_assumptions=0.0,
                normalized_cost=0.0,
            ),
        )
        can_collapse, reason, _ = bc.collapse_decision([first, second])
        self.assertFalse(can_collapse)
        self.assertIn("margin", reason)

    def test_high_information_alternative_blocks_collapse(self):
        """The high-information guard must be reachable, not masked.

        Regression: the guard was evaluated *after* the generic margin check, but
        the band it covers (``margin <= 0.10``) lies inside the generic band
        (``margin < 0.12``) for the reference thresholds. Any margin able to
        satisfy it had therefore already returned with the weaker
        "leader margin is too small" reason, so the branch could never fire.

        The runner-up here carries ``information_gain >= 0.60`` and sits within
        the near-leader margin, so the specific reason must be reported -- and
        while the collapse decision is unchanged, the *reported* reason is what
        an operator acts on.
        """
        leader = bc.Branch(
            "a",
            self.metrics(
                evidence=1.0,
                verification=1.0,
                independence=1.0,
                information_gain=0.90,
                contradiction=0.0,
                unresolved_assumptions=0.0,
                normalized_cost=0.0,
            ),
        )
        runner_up = bc.Branch(
            "b",
            self.metrics(
                evidence=0.95,
                verification=0.95,
                independence=1.0,
                information_gain=0.80,
                contradiction=0.0,
                unresolved_assumptions=0.0,
                normalized_cost=0.0,
            ),
        )
        can_collapse, reason, selected = bc.collapse_decision([leader, runner_up])
        self.assertFalse(can_collapse, reason)
        self.assertEqual(reason, "high-information alternative remains unresolved")
        self.assertEqual(selected.branch_id, "a")

    def test_high_information_guard_is_evaluated_before_the_generic_margin(self):
        """Pin the ordering directly: the same inputs must not fall through.

        Both guards block collapse, so only the reason can distinguish them.
        With the documented order the specific guard wins; with the order the
        audit found, the generic one masks it.
        """
        leader = bc.Branch(
            "a",
            self.metrics(
                evidence=1.0,
                verification=1.0,
                independence=1.0,
                contradiction=0.0,
                unresolved_assumptions=0.0,
                normalized_cost=0.0,
            ),
        )
        runner_up = bc.Branch(
            "b",
            self.metrics(
                evidence=0.95,
                verification=0.95,
                independence=1.0,
                contradiction=0.0,
                unresolved_assumptions=0.0,
                normalized_cost=0.0,
            ),
        )
        leader_score = bc.branch_score(leader.metrics)
        runner_score = bc.branch_score(runner_up.metrics)
        # The audited regime: inside the near-leader band, below the generic band.
        self.assertLessEqual(
            leader_score - runner_score, bc.DEFAULT_THRESHOLDS.unresolved_near_leader_margin
        )
        self.assertLess(
            leader_score - runner_score, bc.DEFAULT_THRESHOLDS.collapse_margin
        )
        can_collapse, reason, _ = bc.collapse_decision([leader, runner_up])
        self.assertFalse(can_collapse)
        self.assertEqual(reason, "high-information alternative remains unresolved")

    def test_high_information_guard_respects_the_configured_margin(self):
        """A near-leader runner-up with low information gain uses the generic rule."""
        leader = bc.Branch(
            "a",
            self.metrics(
                evidence=1.0,
                verification=1.0,
                independence=1.0,
                contradiction=0.0,
                unresolved_assumptions=0.0,
                normalized_cost=0.0,
            ),
        )
        runner_up = bc.Branch(
            "b",
            self.metrics(
                evidence=0.95,
                verification=0.95,
                independence=1.0,
                information_gain=0.10,
                contradiction=0.0,
                unresolved_assumptions=0.0,
                normalized_cost=0.0,
            ),
        )
        can_collapse, reason, _ = bc.collapse_decision([leader, runner_up])
        self.assertFalse(can_collapse)
        self.assertEqual(reason, "leader margin is too small")
        # Outside the near-leader band the alternative no longer blocks collapse.
        can_collapse, reason, _ = bc.collapse_decision(
            [leader, runner_up],
            thresholds=bc.Thresholds(
                collapse_margin=0.05,
                unresolved_near_leader_margin=0.01,
            ),
        )
        self.assertTrue(can_collapse, reason)

    def test_uncertainty_controls_width(self):
        self.assertEqual(bc.recommended_width(0.10), (2, 3))
        self.assertEqual(bc.recommended_width(0.40), (4, 6))
        self.assertEqual(bc.recommended_width(0.90), (6, 10))

    def test_diversity_ratio_detects_duplicates(self):
        ratio = bc.diversity_ratio([0.2, 0.9, 0.4, 0.95], duplicate_threshold=0.85)
        assert_close(ratio, 0.5)

    def test_invalid_metric_fails_fast(self):
        with self.assertRaises(ValueError):
            bc.branch_score(self.metrics(evidence=1.2))


if __name__ == "__main__":
    unittest.main()
