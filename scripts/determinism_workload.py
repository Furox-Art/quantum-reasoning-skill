"""Deterministic falsification-suite workload sampled by the determinism matrix."""

from __future__ import annotations

import importlib.util
import io
import json
import os
import sys
import tempfile
from contextlib import redirect_stdout
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


def build_bundle(root: Path, name: str, evaluate: ModuleType) -> Path:
    bundle = root / name
    bundle.mkdir()
    cases = [{"id": "c1", "domain": "math", "prompt": "1+1?", "accepted_answers": ["2"]}]
    baseline = [{"case_id": "c1", "answer": "2", "tokens": 10, "tool_calls": 0, "latency_ms": 100}]
    skill = [{"case_id": "c1", "answer": "2", "tokens": 12, "tool_calls": 0, "latency_ms": 110}]
    for filename, rows in (
        ("cases.jsonl", cases),
        ("baseline.jsonl", baseline),
        ("skill.jsonl", skill),
    ):
        (bundle / filename).write_text(
            "".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8"
        )
    conditions = {
        "instruction_config": "reference",
        "sampling": {},
        "tool_availability": [],
        "context_limit": None,
        "output_limit": None,
    }
    metadata = {
        "provider": "determinism-matrix",
        "model": "fixed-fixture",
        "run_date": "2026-10-27",
        "skill_version": "1.2.0",
        "repetitions_per_case": 1,
        "failures_recorded": True,
        "baseline": conditions,
        "skill": conditions,
    }
    (bundle / "metadata.json").write_text(json.dumps(metadata), encoding="utf-8")
    summary = {
        "baseline": evaluate.summarize(cases, baseline),
        "skill": evaluate.summarize(cases, skill),
    }
    summary["comparison"] = evaluate.compare(summary["baseline"], summary["skill"])
    (bundle / "comparison.json").write_text(
        json.dumps(summary, sort_keys=True), encoding="utf-8"
    )
    (bundle / "README.md").write_text(
        "Determinism matrix fixture bundle.\n", encoding="utf-8"
    )
    return bundle


def validation_sample(validator: ModuleType, evaluate: ModuleType) -> dict[str, object]:
    """Validate two mixed-case bundles and keep the reported order only.

    The temp root and the bundle paths differ on every run, so the payload must
    not carry them. The order is the deterministic surface: raw-name ordering is
    host-independent, while sorting ``Path`` objects is not.
    """
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        for name in ("Zulu", "alpha"):
            build_bundle(root, name, evaluate)
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            code = validator.main(["--root", str(root)])
        order = [
            Path(line.removeprefix("validated ")).name
            for line in buffer.getvalue().splitlines()
        ]
    return {"exit": code, "order": order}


def main() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo_root))
    suite_dir = repo_root / "quantum_reasoning_skill" / "benchmark" / "falsification"
    runner = load("determinism_falsification_run_suite", suite_dir / "run_suite.py")
    scenarios = load("determinism_falsification_scenarios", suite_dir / "scenarios.py")
    evaluator = load(
        "determinism_benchmark_evaluate",
        repo_root / "quantum_reasoning_skill" / "benchmark" / "evaluate.py",
    )
    from quantum_reasoning_skill.benchmark import evaluate as package_evaluate
    from quantum_reasoning_skill.benchmark import validate_submission as validator

    results = runner.run_suite(scenarios.build_all_scenarios())
    payload = strip_latency(
        {
            "summary": runner.aggregate(results),
            "per_scenario": runner.results_to_dicts(results),
            "reliability": runner.reliability_rows(results),
        }
    )
    payload["evaluation"] = evaluation_sample(evaluator)
    payload["validation"] = validation_sample(validator, package_evaluate)
    if (
        not payload["summary"]
        or not payload["per_scenario"]
        or not payload["evaluation"]["skill"]["cases_evaluated"]
    ):
        raise SystemExit("workload produced empty results; it is vacuous")
    if payload["validation"]["exit"] != 0 or payload["validation"]["order"] != [
        "Zulu",
        "alpha",
    ]:
        raise SystemExit(
            "bundle validation did not report the fixtures in raw-name order"
        )
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
