"""Cross-process determinism of the falsification benchmark.

The full suite runs in two fresh interpreters whose only difference is
``PYTHONHASHSEED``. Wall-clock latency is legitimately different every run and
is stripped; every other field -- branch states, switches, revivals, answers,
probabilities, token counts and aggregate metrics -- must be byte-identical.
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


runner = load("cross_process_falsification_run_suite", suite_dir / "run_suite.py")
scenarios = load("cross_process_falsification_scenarios", suite_dir / "scenarios.py")

results = runner.run_suite(scenarios.build_all_scenarios())
payload = {
    "summary": runner.aggregate(results),
    "per_scenario": runner.results_to_dicts(results),
    "reliability": runner.reliability_rows(results),
}


def strip_latency(value):
    if isinstance(value, dict):
        return {key: strip_latency(item) for key, item in value.items() if "latency" not in key}
    if isinstance(value, list):
        return [strip_latency(item) for item in value]
    return value


print(json.dumps(strip_latency(payload), ensure_ascii=False))
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


if __name__ == "__main__":
    unittest.main()
