"""Uncertainty estimates cannot turn NaN or infinity into fake certainty."""

from __future__ import annotations

import unittest

from quantum_reasoning_skill.reference.branch_controller import normalized_entropy


class NonfiniteEntropyRegressionTests(unittest.TestCase):
    def test_nan_and_infinities_fail_closed(self) -> None:
        for bad in (float("nan"), float("inf"), -float("inf")):
            with self.subTest(value=bad), self.assertRaises(ValueError):
                normalized_entropy([0.5, bad])

    def test_finite_total_overflow_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            normalized_entropy([1e308, 1e308])

    def test_finite_probabilities_remain_supported(self) -> None:
        self.assertEqual(normalized_entropy([0.0, 0.0]), 0.0)
        self.assertEqual(normalized_entropy([1.0, 1.0]), 1.0)
