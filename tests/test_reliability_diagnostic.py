"""Tests for the synthetic score-outcome reliability diagnostic.

The diagnostic is explicitly synthetic: it checks the harness's calibration
measurement machinery against seeded pseudo-random data with known calibration,
not any language model. These tests pin that labeling, the measurement math,
the fail-closed input validation, the negative control (known miscalibration
must raise ECE), determinism across processes and hash seeds, and both CLI
entry points.
"""

from __future__ import annotations

import contextlib
import importlib
import io
import json
import math
import os
import runpy
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import conftest  # noqa: E402  (repository root is on sys.path only after the insert)

reliability = importlib.import_module("quantum_reasoning_skill.benchmark.reliability")

assert_close = conftest.assert_close


class SyntheticGeneratorTests(unittest.TestCase):
    def test_same_seed_reproduces_the_same_pairs(self):
        first = reliability.generate_synthetic_pairs(7, 200)
        second = reliability.generate_synthetic_pairs(7, 200)
        self.assertEqual(first, second)
        self.assertNotEqual(first, reliability.generate_synthetic_pairs(8, 200))

    def test_pairs_stay_inside_the_contract(self):
        pairs = reliability.generate_synthetic_pairs(1, 500)
        self.assertEqual(len(pairs), 500)
        for score, outcome in pairs:
            self.assertGreaterEqual(score, 0.0)
            self.assertLess(score, 1.0)
            self.assertIn(outcome, (0, 1))

    def test_nonpositive_sample_count_is_rejected(self):
        for samples in (0, -3):
            with self.assertRaises(ValueError):
                reliability.generate_synthetic_pairs(1, samples)

    def test_nonfinite_or_oversized_shift_is_rejected(self):
        for shift in (math.nan, math.inf, -math.inf, 1.5, -1.5):
            with self.assertRaises(ValueError):
                reliability.generate_synthetic_pairs(1, 10, miscalibration=shift)

    def test_extreme_shifts_clip_to_certain_outcomes(self):
        high = reliability.generate_synthetic_pairs(3, 300, miscalibration=1.0)
        low = reliability.generate_synthetic_pairs(3, 300, miscalibration=-1.0)
        self.assertTrue(all(outcome == 1 for _, outcome in high))
        self.assertTrue(all(outcome == 0 for _, outcome in low))

    def test_zero_shift_is_calibrated_by_construction(self):
        pairs = reliability.generate_synthetic_pairs(11, 20_000)
        mean_score = sum(score for score, _ in pairs) / len(pairs)
        outcome_rate = sum(outcome for _, outcome in pairs) / len(pairs)
        # Sampling noise only; a loose bound keeps the test robust across seeds.
        self.assertLess(abs(mean_score - outcome_rate), 0.05)


class ValidationTests(unittest.TestCase):
    def test_empty_pairs_are_rejected(self):
        with self.assertRaises(ValueError):
            reliability.reliability_diagnostic([])

    def test_nonpositive_bin_count_is_rejected(self):
        for bins in (0, -2):
            with self.assertRaises(ValueError):
                reliability.reliability_diagnostic([(0.5, 1)], bins=bins)

    def test_malformed_pair_shapes_are_rejected(self):
        for pair in (None, "x", 0.5):
            with self.assertRaises(TypeError):
                reliability.reliability_diagnostic([pair])
        for pair in ((0.5,), (0.5, 1, 2)):
            with self.assertRaises(ValueError):
                reliability.reliability_diagnostic([pair])

    def test_bad_score_types_are_rejected(self):
        for score in (True, "0.5", None):
            with self.assertRaises(TypeError):
                reliability.reliability_diagnostic([(score, 1)])

    def test_bad_score_values_are_rejected(self):
        for score in (math.nan, math.inf, -0.1, 1.5):
            with self.assertRaises(ValueError):
                reliability.reliability_diagnostic([(score, 1)])

    def test_bad_outcome_types_are_rejected(self):
        for outcome in (True, "1", 0.5, None):
            with self.assertRaises(TypeError):
                reliability.reliability_diagnostic([(0.5, outcome)])

    def test_bad_outcome_values_are_rejected(self):
        for outcome in (2, -1):
            with self.assertRaises(ValueError):
                reliability.reliability_diagnostic([(0.5, outcome)])

    def test_list_pairs_and_integer_scores_are_accepted(self):
        result = reliability.reliability_diagnostic([[0, 0], [1, 1]], bins=2)
        assert_close(result["expected_calibration_error"], 0.0)
        assert_close(result["brier_score"], 0.0)


class MeasurementTests(unittest.TestCase):
    def test_hand_computed_two_bin_case(self):
        pairs = [(0.05, 0), (0.15, 1), (0.95, 1)]
        result = reliability.reliability_diagnostic(pairs, bins=2)
        low, high = result["bins"]
        self.assertEqual(low["count"], 2)
        assert_close(low["mean_score"], 0.1)
        assert_close(low["outcome_rate"], 0.5)
        self.assertEqual(high["count"], 1)
        assert_close(high["mean_score"], 0.95)
        assert_close(high["outcome_rate"], 1.0)
        assert_close(result["expected_calibration_error"], (2 * 0.4 + 1 * 0.05) / 3)
        assert_close(result["brier_score"], (0.05**2 + 0.85**2 + 0.05**2) / 3)
        assert_close(result["mean_score"], (0.05 + 0.15 + 0.95) / 3)
        assert_close(result["outcome_rate"], 2 / 3)
        self.assertEqual(result["samples"], 3)
        self.assertEqual(result["bin_count"], 2)

    def test_score_one_lands_in_the_last_bin(self):
        result = reliability.reliability_diagnostic([(1.0, 1)], bins=10)
        self.assertEqual(result["bins"][-1]["count"], 1)
        self.assertEqual(sum(row["count"] for row in result["bins"]), 1)

    def test_empty_bins_report_not_measured(self):
        result = reliability.reliability_diagnostic([(0.05, 0), (0.95, 1)], bins=10)
        empty = [row for row in result["bins"] if row["count"] == 0]
        self.assertEqual(len(empty), 8)
        for row in empty:
            self.assertIsNone(row["mean_score"])
            self.assertIsNone(row["outcome_rate"])

    def test_known_miscalibration_is_measured(self):
        # Every score claims 0.9 while every outcome is 0: ECE must be 0.9.
        result = reliability.reliability_diagnostic([(0.9, 0)] * 4, bins=5)
        assert_close(result["expected_calibration_error"], 0.9)
        assert_close(result["brier_score"], 0.81)


class SyntheticDiagnosticTests(unittest.TestCase):
    def test_payload_is_explicitly_labeled_synthetic(self):
        payload = reliability.run_synthetic_diagnostic(samples=200)
        self.assertIs(payload["synthetic"], True)
        self.assertEqual(payload["data"], "synthetic")
        self.assertEqual(payload["diagnostic"], "score-outcome-reliability")
        disclaimer = payload["disclaimer"].lower()
        self.assertIn("synthetic", disclaimer)
        self.assertIn("no claim", disclaimer)
        self.assertEqual(payload["generator"]["seed"], reliability.DEFAULT_SEED)
        self.assertEqual(payload["generator"]["samples"], 200)
        self.assertEqual(payload["generator"]["miscalibration_shift"], 0.0)

    def test_negative_control_known_miscalibration_raises_ece(self):
        calibrated = reliability.run_synthetic_diagnostic(samples=20_000)
        overconfident = reliability.run_synthetic_diagnostic(
            samples=20_000, miscalibration=0.25
        )
        underconfident = reliability.run_synthetic_diagnostic(
            samples=20_000, miscalibration=-0.25
        )
        # Bounds measured for seed 2026: calibrated ECE ~0.008, shifted ~0.22.
        self.assertLess(calibrated["expected_calibration_error"], 0.05)
        self.assertGreater(overconfident["expected_calibration_error"], 0.1)
        self.assertGreater(underconfident["expected_calibration_error"], 0.1)
        self.assertLess(
            calibrated["expected_calibration_error"],
            overconfident["expected_calibration_error"],
        )

    def test_identical_inputs_render_byte_identical_json(self):
        first = json.dumps(reliability.run_synthetic_diagnostic(samples=500), sort_keys=True)
        second = json.dumps(reliability.run_synthetic_diagnostic(samples=500), sort_keys=True)
        self.assertEqual(first, second)


class CliTests(unittest.TestCase):
    def run_main(self, argv):
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = reliability.main(argv)
        return code, stdout.getvalue(), stderr.getvalue()

    def test_default_run_prints_labeled_json(self):
        code, out, err = self.run_main(["--samples", "300"])
        self.assertEqual(code, 0)
        self.assertEqual(err, "")
        payload = json.loads(out)
        self.assertIs(payload["synthetic"], True)
        self.assertEqual(payload["samples"], 300)
        self.assertIn('"synthetic": true', out)

    def test_invalid_arguments_exit_two(self):
        for argv in (
            ["--samples", "0"],
            ["--bins", "0"],
            ["--miscalibration", "nan"],
            ["--miscalibration", "2"],
        ):
            with self.assertRaises(SystemExit) as caught:
                self.run_main(argv)
            self.assertEqual(caught.exception.code, 2)

    def test_output_artifact_matches_stdout(self):
        with tempfile.TemporaryDirectory() as tmp:
            previous = Path.cwd()
            os.chdir(tmp)
            try:
                code, out, _ = self.run_main(["--samples", "300", "--output", "diag.json"])
                self.assertEqual(code, 0)
                written = (Path(tmp) / "diag.json").read_text(encoding="utf-8")
                # print(rendered) already appends the trailing newline that the
                # artifact writes explicitly, so the two are byte-identical.
                self.assertEqual(written, out)
                self.assertIs(json.loads(written)["synthetic"], True)
            finally:
                os.chdir(previous)

    def test_output_escaping_the_working_directory_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            inner = Path(tmp) / "inner"
            inner.mkdir()
            previous = Path.cwd()
            os.chdir(inner)
            try:
                code, _, err = self.run_main(
                    ["--samples", "100", "--output", "../outside.json"]
                )
                self.assertEqual(code, 2)
                self.assertIn("--output", err)
                self.assertFalse((Path(tmp) / "outside.json").exists())
            finally:
                os.chdir(previous)

    def test_main_guard_block_executes(self):
        """The ``if __name__ == "__main__"`` block runs, in-process, via runpy."""
        argv = ["reliability", "--samples", "100"]
        with mock.patch.object(sys, "argv", argv), contextlib.redirect_stdout(
            io.StringIO()
        ), self.assertRaises(SystemExit) as caught:
            runpy.run_module(
                "quantum_reasoning_skill.benchmark.reliability", run_name="__main__"
            )
        self.assertEqual(caught.exception.code, 0)


class EntryPointTests(unittest.TestCase):
    """Both documented entry points run, and output is hash-seed stable."""

    def run_child(self, args, hash_seed):
        env = dict(os.environ)
        env["PYTHONHASHSEED"] = str(hash_seed)
        return subprocess.run(
            [sys.executable, *args],
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )

    def test_module_entry_point(self):
        result = self.run_child(
            ["-m", "quantum_reasoning_skill.benchmark.reliability", "--samples", "500"], 1
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIs(json.loads(result.stdout)["synthetic"], True)

    def test_direct_script_entry_point(self):
        script = ROOT / "quantum_reasoning_skill" / "benchmark" / "reliability.py"
        result = self.run_child([str(script), "--samples", "500"], 1)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIs(json.loads(result.stdout)["synthetic"], True)

    def test_help_exits_zero(self):
        result = self.run_child(
            ["-m", "quantum_reasoning_skill.benchmark.reliability", "--help"], 1
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--miscalibration", result.stdout)

    def test_output_is_identical_across_hash_seeds(self):
        args = ["-m", "quantum_reasoning_skill.benchmark.reliability", "--samples", "2000"]
        first = self.run_child(args, 1)
        second = self.run_child(args, 99)
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertEqual(first.stdout, second.stdout)


if __name__ == "__main__":
    unittest.main()
