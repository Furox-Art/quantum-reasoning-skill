"""Prove malformed confidence, disk denial and CLI fallback cannot be hidden."""

from __future__ import annotations

import builtins
import dataclasses
import json
import runpy
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from quantum_reasoning_skill.benchmark import evaluate, validate_submission
from quantum_reasoning_skill.benchmark.falsification import run_suite, scenarios


def _input_pair(root):
    case = root / "cases.jsonl"
    skill = root / "skill.jsonl"
    case.write_text(json.dumps({"id": "one", "domain": "math", "prompt": "1?", "accepted_answers": ["1"]}) + "\n")
    skill.write_text(json.dumps({"case_id": "one", "answer": "1", "tokens": 2, "tool_calls": 0, "latency_ms": 1}) + "\n")
    return case, skill


class AdversarialProbabilityGuardTests(unittest.TestCase):
    def test_probability_bin_rejects_overconfident_or_nonfinite_value(self):
        real = run_suite.run_suite(scenarios.build_control_scenarios()[:1])[0]
        for value in (1.5, -0.1, float("nan"), float("inf")):
            fake = dataclasses.replace(real, probability_rows=[
                {"step": 1, "truth": "H_A", "probabilities": {"H_A": value}},
            ])
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "truth probability"):
                run_suite.reliability_rows([fake])

    def test_legal_reliability_interval_boundaries_stay_deterministic(self):
        real = run_suite.run_suite(scenarios.build_control_scenarios()[:1])[0]
        for value, expected in ((0.0, "0.0-0.2"), (0.2, "0.0-0.2"),
                                (0.5, "0.4-0.6"), (1.0, "0.8-1.0")):
            fake = dataclasses.replace(real, probability_rows=[
                {"step": 1, "truth": "H_A", "probabilities": {"H_A": value}},
            ])
            with self.subTest(value=value):
                self.assertEqual(run_suite.reliability_rows([fake])[0]["bin"], expected)

    def test_report_formatting_also_handles_exact_integer_telemetry(self):
        examples = run_suite.run_suite(scenarios.build_control_scenarios()[:1])
        summary = run_suite.aggregate(examples)
        summary["single"]["accuracy"] = 1
        report = run_suite.render_markdown_table(summary, examples)
        self.assertIn("| overall accuracy | 1 |", report)

    def test_unknown_revival_target_is_not_invented_from_unrelated_evidence(self):
        sample = scenarios.build_revival_scenarios()[0]
        changed = dataclasses.replace(sample, revived_branch="unobserved", revival_step=1)
        result = run_suite._run_multi_policy(changed)
        self.assertFalse(result.revival_success)


class StrictEntrypointGuardTests(unittest.TestCase):
    def test_error_if_evaluator_produces_non_object_summary(self):
        with tempfile.TemporaryDirectory() as td:
            case, skill = _input_pair(Path(td))
            with patch.object(evaluate, "summarize", return_value=None), self.assertRaisesRegex(ValueError, "must be a JSON object"):
                evaluate.main(["--cases", str(case), "--skill", str(skill)])

    def test_cli_without_output_path_reports_finite_summary_on_stdout(self):
        with tempfile.TemporaryDirectory() as td:
            case, skill = _input_pair(Path(td))
            stdout = StringIO()
            with redirect_stdout(stdout):
                rc = evaluate.main(["--cases", str(case), "--skill", str(skill)])
            self.assertEqual(rc, 0)
            self.assertEqual(json.loads(stdout.getvalue())["skill"]["accuracy"], 1.0)

    def test_validator_loaders_translate_actual_io_denial(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "unreadable.json"
            path.write_text("{}")
            with patch.object(validate_submission.evaluate, "read_text_limited", side_effect=PermissionError("file denied")):
                for loader in (validate_submission.load_json, validate_submission.load_text):
                    with self.subTest(loader=loader.__name__), self.assertRaisesRegex(ValueError, "unreadable"):
                        loader(path)

    def test_plain_script_mode_loads_exact_package_after_initial_import_failure(self):
        original_import = builtins.__import__
        blocked = [True]
        def fail_once(name, *args, **kwargs):
            if name == "quantum_reasoning_skill.benchmark" and blocked[0]:
                blocked[0] = False
                raise ImportError("module path unavailable to plain script")
            return original_import(name, *args, **kwargs)
        with tempfile.TemporaryDirectory() as td:
            argv = ["validate_submission.py", "--root", td, "--allow-empty"]
            path = Path(validate_submission.__file__)
            with patch.object(sys, "argv", argv), patch.object(builtins, "__import__", fail_once), self.assertRaises(SystemExit) as stopped:
                runpy.run_path(str(path), run_name="__main__")
            self.assertEqual(stopped.exception.code, 0)
            self.assertFalse(blocked[0])


if __name__ == "__main__":
    unittest.main()
