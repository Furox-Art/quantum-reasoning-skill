from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "branch_controller", ROOT / "reference" / "branch_controller.py"
)
assert SPEC and SPEC.loader
bc = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = bc
SPEC.loader.exec_module(bc)


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
                contradiction=0.0,
                unresolved_assumptions=0.0,
                normalized_cost=0.0,
            ),
        )
        can_collapse, reason, _ = bc.collapse_decision([first, second])
        self.assertFalse(can_collapse)
        self.assertIn("margin", reason)

    def test_uncertainty_controls_width(self):
        self.assertEqual(bc.recommended_width(0.10), (2, 3))
        self.assertEqual(bc.recommended_width(0.40), (4, 6))
        self.assertEqual(bc.recommended_width(0.90), (6, 10))

    def test_diversity_ratio_detects_duplicates(self):
        ratio = bc.diversity_ratio([0.2, 0.9, 0.4, 0.95], duplicate_threshold=0.85)
        self.assertEqual(ratio, 0.5)

    def test_invalid_metric_fails_fast(self):
        with self.assertRaises(ValueError):
            bc.branch_score(self.metrics(evidence=1.2))


if __name__ == "__main__":
    unittest.main()
