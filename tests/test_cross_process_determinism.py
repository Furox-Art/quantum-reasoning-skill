"""Cross-process determinism of the falsification benchmark and evaluator.

The full suite runs in two fresh interpreters whose only difference is
``PYTHONHASHSEED``. Wall-clock latency is legitimately different every run and
is stripped; every other field -- branch states, switches, revivals, answers,
probabilities, token counts and aggregate metrics -- must be byte-identical.
The evaluator sample measures the same property for ``summarize``/``compare``.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

CHILD = r'''
import importlib.util
import json
import sys
from pathlib import Path

repo_root = Path(sys.argv[1])
suite_dir = repo_root / "quantum_reasoning_skill" / "benchmark" / "falsification"


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def strip_latency(value):
    if isinstance(value, dict):
        return {key: strip_latency(item) for key, item in value.items() if "latency" not in key}
    if isinstance(value, list):
        return [strip_latency(item) for item in value]
    return value


runner = load("cross_process_falsification_run_suite", suite_dir / "run_suite.py")
scenarios = load("cross_process_falsification_scenarios", suite_dir / "scenarios.py")
evaluator = load(
    "cross_process_benchmark_evaluate",
    repo_root / "quantum_reasoning_skill" / "benchmark" / "evaluate.py",
)

results = runner.run_suite(scenarios.build_all_scenarios())
eval_cases = [
    {"id": "eval-1", "domain": "optics", "prompt": "p", "accepted_answers": ["Yes"]},
    {"id": "eval-2", "domain": "arithmetic", "prompt": "p", "accepted_answers": ["42"]},
]
eval_skill = [
    {"case_id": "eval-2", "answer": " 42 ", "tokens": 10, "tool_calls": 0, "latency_ms": 5}
]
eval_baseline = [
    {"case_id": "eval-1", "answer": "no", "tokens": 20, "tool_calls": 1, "latency_ms": 9},
    {"case_id": "eval-2", "answer": "42", "tokens": 30, "tool_calls": 2, "latency_ms": 7},
]
eval_skill_summary = evaluator.summarize(eval_cases, eval_skill)
eval_baseline_summary = evaluator.summarize(eval_cases, eval_baseline)
payload = strip_latency(
    {
        "summary": runner.aggregate(results),
        "per_scenario": runner.results_to_dicts(results),
        "reliability": runner.reliability_rows(results),
    }
)
# Evaluator latency fields come from the measured input rows, not a wall clock,
# so they stay in the compared payload.
payload["evaluation"] = {
    "skill": eval_skill_summary,
    "baseline": eval_baseline_summary,
    "comparison": evaluator.compare(eval_baseline_summary, eval_skill_summary),
}

print(json.dumps(payload, ensure_ascii=False))
'''


def _run_with_hash_seed(seed: str) -> str:
    env = {
        **os.environ,
        "PYTHONHASHSEED": seed,
        "PYTHONIOENCODING": "utf-8",
    }
    completed = subprocess.run(
        [sys.executable, "-c", CHILD, str(REPO_ROOT)],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=300,
        check=False,
    )
    if completed.returncode != 0:
        raise AssertionError(f"child workload failed: {completed.stderr}")
    return completed.stdout


class CrossProcessDeterminismTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.first = _run_with_hash_seed("0")
        cls.second = _run_with_hash_seed("12345")

    def test_suite_is_byte_identical_across_hash_seeds(self):
        self.assertTrue(self.first.strip())
        self.assertEqual(self.first.strip(), self.second.strip())

    def test_workload_is_not_vacuous(self):
        payload = json.loads(self.first)
        self.assertEqual(payload["summary"]["single"]["scenarios"], 9)
        self.assertEqual(payload["summary"]["multi"]["scenarios"], 9)
        self.assertEqual(len(payload["per_scenario"]), 18)
        self.assertEqual(payload["summary"]["multi"]["accuracy"], 1.0)
        self.assertTrue(payload["reliability"])
        for row in payload["per_scenario"]:
            self.assertNotIn("total_latency_ms", row)
            for step in row["steps"]:
                self.assertNotIn("latency_ms", step)
        evaluation = payload["evaluation"]
        self.assertEqual(evaluation["skill"]["cases_evaluated"], 1)
        self.assertEqual(evaluation["skill"]["missing_case_ids"], ["eval-1"])
        self.assertEqual(evaluation["skill"]["accuracy"], 1.0)
        self.assertEqual(evaluation["baseline"]["accuracy"], 0.5)
        self.assertEqual(evaluation["comparison"]["accuracy_delta"], 0.5)
        self.assertEqual(evaluation["skill"]["mean_latency_ms"], 5.0)


if __name__ == "__main__":
    unittest.main()
