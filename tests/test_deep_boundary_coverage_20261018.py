"""Boundary decisions, actual entrypoints and nonfabrication for adversarial input."""

from __future__ import annotations

import dataclasses
import importlib.util
import json
import runpy
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

import benchmark
from benchmark import evaluate
from benchmark.falsification import run_suite, scenarios
from reference import branch_controller as bc


def _snapshot(**overrides):
    values = {"evidence": 1.0, "verification": 1.0, "independence": 1.0,
              "information_gain": 1.0, "contradiction": 0.0,
              "unresolved_assumptions": 0.0, "normalized_cost": 0.0}
    values.update(overrides)
    return values


def _scenario(step, **overrides):
    values = {"id": "boundary-case", "scenario_type": "control", "domain": "test",
              "prompt": "An explicit branch decision?", "truth_branch": "H_A",
              "answer": "H_A", "accepted_answers": ["H_A"], "decoy_branch": None,
              "falsified_at_step": None, "revival_step": None, "revived_branch": None,
              "steps": [step], "notes": "synthetic boundary with recorded metrics"}
    values.update(overrides)
    return scenarios.Scenario(**values)


class StrictControllerBoundaryTests(unittest.TestCase):
    def test_verification_gate_refuses_an_unverified_leader(self):
        candidate = bc.Branch("H_A", bc.BranchMetrics(**_snapshot(verification=0.7)))
        t = bc.Thresholds(collapse_score=0.1, collapse_verification=0.8)
        decision = bc.collapse_decision([candidate], thresholds=t)
        self.assertFalse(decision[0])
        self.assertIn("verification below", decision[1])

    def test_contradiction_gate_refuses_an_unresolved_claim(self):
        candidate = bc.Branch("H_A", bc.BranchMetrics(**_snapshot(contradiction=0.3)))
        t = bc.Thresholds(collapse_score=0.1, collapse_verification=0.2,
                          collapse_max_contradiction=0.1)
        decision = bc.collapse_decision([candidate], thresholds=t)
        self.assertFalse(decision[0])
        self.assertIn("contradiction remains too high", decision[1])

    def test_single_verified_candidate_can_collapse_without_shortcut(self):
        step = scenarios.EvidenceStep(step=1, metrics={"H_A": _snapshot()}, answer_known_from=True)
        outcome = run_suite._run_multi_policy(_scenario(step))
        self.assertTrue(outcome.steps[0].collapsed)
        self.assertTrue(outcome.correct)
        self.assertEqual(outcome.final_answer, "H_A")

    def test_fully_contradicted_branch_cannot_invent_a_surviving_leader(self):
        step = scenarios.EvidenceStep(step=1, metrics={"H_A": _snapshot(contradiction=1.0)})
        outcome = run_suite._run_multi_policy(_scenario(step))
        self.assertEqual(outcome.final_answer, "")
        self.assertFalse(outcome.correct)

    def test_decoy_known_to_be_other_than_first_leader_counts_immediate_switch(self):
        original = scenarios.build_falsification_scenarios()[0]
        first = run_suite._run_single_policy(original)
        alt = "H_C" if first.final_answer != "H_C" else "H_B"
        changed = dataclasses.replace(original, decoy_branch=alt)
        result = run_suite._run_single_policy(changed)
        self.assertTrue(result.switch_success)
        self.assertEqual(result.switch_delay_steps, 0)

    def test_multi_policy_keeps_failed_switch_visible(self):
        original = scenarios.build_falsification_scenarios()[0]
        changed = dataclasses.replace(original, truth_branch="unattested_truth")
        result = run_suite._run_multi_policy(changed)
        self.assertFalse(result.switch_success)
        self.assertIsNone(result.switch_delay_steps)
        self.assertFalse(result.correct)

    def test_zero_confidence_exponential_fallback_is_normalized_not_nan(self):
        with patch("builtins.pow", return_value=0.0):
            self.assertEqual(run_suite._softmax_scores({"a": 0.8, "b": 0.3}), {"a": 0.5, "b": 0.5})

    def test_empty_brier_rows_are_explicitly_zero(self):
        self.assertEqual(run_suite._brier_from_rows([]), 0.0)

    def test_scenario_serialization_preserves_original_evidence_stream(self):
        examples = scenarios.build_all_scenarios()
        serialized = scenarios.scenarios_to_dict(examples)
        self.assertEqual(len(serialized), len(examples))
        self.assertEqual(serialized[0]["steps"][0]["metrics"], examples[0].steps[0].metrics)
        self.assertEqual(json.loads(json.dumps(serialized, allow_nan=False)), serialized)


class RealCommandEntryPointContracts(unittest.TestCase):
    def test_real_falsification_entrypoint_writes_isolated_artifacts(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            args = ["run_suite.py", "--output-dir", str(root / "results"),
                    "--cases-output", str(root / "cases.jsonl"), "--quiet"]
            with patch.object(sys, "argv", args), self.assertRaises(SystemExit) as stopped:
                runpy.run_module("benchmark.falsification.run_suite", run_name="__main__")
            self.assertEqual(stopped.exception.code, 0)
            self.assertTrue((root / "results" / "results.json").is_file())

    def test_real_evaluator_entrypoint_reports_typed_missing_input(self):
        with tempfile.TemporaryDirectory() as td:
            args = ["evaluate.py", "--cases", str(Path(td) / "not-created.jsonl"),
                    "--skill", str(Path(td) / "not-created-results.jsonl")]
            with patch.object(sys, "argv", args), self.assertRaises(SystemExit) as stopped:
                runpy.run_module("benchmark.evaluate", run_name="__main__")
            self.assertEqual(stopped.exception.code, evaluate.EXIT_MISSING_INPUT)

    def test_actual_validator_entrypoint_accepts_explicit_empty_root_only(self):
        with tempfile.TemporaryDirectory() as td:
            args = ["validate_submission.py", "--root", td, "--allow-empty"]
            with patch.object(sys, "argv", args), self.assertRaises(SystemExit) as stopped:
                runpy.run_module("benchmark.validate_submission", run_name="__main__")
            self.assertEqual(stopped.exception.code, 0)

    def test_complete_package_verification_rejects_missing_module(self):
        real = Path.is_file
        def missing(path):
            if path.name == "evaluate.py" and path.parent == benchmark.package_root():
                return False
            return real(path)
        with patch.object(Path, "is_file", missing), self.assertRaisesRegex(ImportError, "incomplete"):
            benchmark._verify_integrity()

    def test_loadable_script_without_repo_sys_path_recovers_package_root(self):
        root = Path(run_suite.__file__).resolve().parents[2]
        spec = importlib.util.spec_from_file_location("isolated_boundary_run_suite", run_suite.__file__)
        self.assertIsNotNone(spec)
        module = importlib.util.module_from_spec(spec)
        with patch.object(sys, "path", [entry for entry in sys.path if entry != str(root)]), patch.dict(sys.modules, {spec.name: module}):
            spec.loader.exec_module(module)
            self.assertIn(str(root), sys.path)
            self.assertTrue(callable(module.run_suite))

    def test_cli_baseline_comparison_uses_actual_replayed_rows(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            case = {"id": "one", "domain": "math", "prompt": "1+0?", "accepted_answers": ["1"]}
            result = {"case_id": "one", "answer": "1", "tokens": 2, "tool_calls": 0, "latency_ms": 4}
            paths = [root / name for name in ("cases.jsonl", "baseline.jsonl", "skill.jsonl")]
            for path, value in zip(paths, (case, result, result), strict=True):
                path.write_text(json.dumps(value) + "\n")
            output = root / "comparison.json"
            with redirect_stdout(StringIO()):
                rc = evaluate.main(["--cases", str(paths[0]), "--baseline", str(paths[1]),
                                    "--skill", str(paths[2]), "--cases-dir", td,
                                    "--output", str(output)])
            self.assertEqual(rc, 0)
            saved = json.loads(output.read_text())
            self.assertEqual(saved["baseline"]["accuracy"], 1.0)
            self.assertEqual(saved["comparison"]["accuracy_delta"], 0.0)


if __name__ == "__main__":
    unittest.main()
