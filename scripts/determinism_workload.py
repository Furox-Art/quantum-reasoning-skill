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


def evaluation_sample(evaluator: ModuleType) -> dict[str, object]:
    cases = [
        {
            "id": "case-alpha",
            "domain": "optics",
            "prompt": "Which effect bends light at a boundary?",
            "accepted_answers": ["Refraction", "bending"],
        },
        {
            "id": "case-beta",
            "domain": "arithmetic",
            "prompt": "What is six times seven?",
            "accepted_answers": ["42"],
        },
        {
            "id": "case-gamma",
            "domain": "logic",
            "prompt": "Is the statement consistent?",
            "accepted_answers": ["yes"],
        },
    ]
    skill_rows = [
        {
            "case_id": "case-alpha",
            "answer": "  REFRACTION ",
            "tokens": 120,
            "tool_calls": 1,
            "latency_ms": 900,
            "branches_total": 4,
            "branches_distinct": 3,
            "revived_branches": 1,
            "recovered_errors": 0,
            "contradictions_found": 2,
            "contradictions_resolved": 1,
        },
        {
            "case_id": "case-beta",
            "answer": "42",
            "tokens": 80,
            "tool_calls": 0,
            "latency_ms": 500,
            "branches_total": 3,
            "branches_distinct": 2,
            "revived_branches": 0,
            "recovered_errors": 1,
            "contradictions_found": 0,
            "contradictions_resolved": 0,
        },
    ]
    baseline_rows = [
        {
            "case_id": "case-alpha",
            "answer": "reflection",
            "tokens": 150,
            "tool_calls": 2,
            "latency_ms": 1100,
            "branches_total": 2,
            "branches_distinct": 2,
            "revived_branches": 0,
            "recovered_errors": 0,
            "contradictions_found": 1,
            "contradictions_resolved": 0,
        },
        {
            "case_id": "case-beta",
            "answer": "42",
            "tokens": 100,
            "tool_calls": 1,
            "latency_ms": 600,
        },
        {
            "case_id": "case-gamma",
            "answer": "yes",
            "tokens": 90,
            "tool_calls": 1,
            "latency_ms": 550,
        },
    ]
    skill = evaluator.summarize(cases, skill_rows)
    baseline = evaluator.summarize(cases, baseline_rows)
    return {
        "skill": skill,
        "baseline": baseline,
        "comparison": evaluator.compare(baseline, skill),
    }


def main() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    suite_dir = repo_root / "quantum_reasoning_skill" / "benchmark" / "falsification"
    runner = load("determinism_falsification_run_suite", suite_dir / "run_suite.py")
    scenarios = load("determinism_falsification_scenarios", suite_dir / "scenarios.py")
    evaluator = load(
        "determinism_benchmark_evaluate",
        repo_root / "quantum_reasoning_skill" / "benchmark" / "evaluate.py",
    )

    results = runner.run_suite(scenarios.build_all_scenarios())
    payload = strip_latency(
        {
            "summary": runner.aggregate(results),
            "per_scenario": runner.results_to_dicts(results),
            "reliability": runner.reliability_rows(results),
        }
    )
    payload["evaluation"] = evaluation_sample(evaluator)
    if (
        not payload["summary"]
        or not payload["per_scenario"]
        or not payload["evaluation"]["skill"]["cases_evaluated"]
    ):
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
