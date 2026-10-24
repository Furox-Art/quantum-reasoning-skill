"""Deterministic falsification-suite workload sampled by the determinism matrix."""

from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path
from types import ModuleType


def load(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise SystemExit(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def strip_latency(value: object) -> object:
    if isinstance(value, dict):
        return {key: strip_latency(item) for key, item in value.items() if "latency" not in key}
    if isinstance(value, list):
        return [strip_latency(item) for item in value]
    return value


def main() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    suite_dir = repo_root / "quantum_reasoning_skill" / "benchmark" / "falsification"
    runner = load("determinism_falsification_run_suite", suite_dir / "run_suite.py")
    scenarios = load("determinism_falsification_scenarios", suite_dir / "scenarios.py")

    results = runner.run_suite(scenarios.build_all_scenarios())
    payload = strip_latency(
        {
            "summary": runner.aggregate(results),
            "per_scenario": runner.results_to_dicts(results),
            "reliability": runner.reliability_rows(results),
        }
    )
    if not payload["summary"] or not payload["per_scenario"]:
        raise SystemExit("workload produced empty results; it is vacuous")
    artifact_dir = os.environ.get("DETERMINISM_ARTIFACT_DIR")
    if artifact_dir:
        Path(artifact_dir, "payload.json").write_text(
            json.dumps(payload, ensure_ascii=False, sort_keys=True),
            encoding="utf-8",
            newline="\n",
        )
    print(json.dumps(payload, ensure_ascii=False))


if __name__ == "__main__":
    main()
