#!/usr/bin/env python3
"""Executable quickstart verification for the Quantum Reasoning Skill.

This script prints the real state of a checkout. It does not fabricate metrics and
it does not run any language model. Every number it prints is computed from files in
this repository or from the explicitly synthetic placeholder rows written in step 4.

Run it from a clone:

    python docs/quickstart.py

Exit code 0 means every structural check passed. No exit code means "the skill
improves reasoning" - that claim requires a baseline-vs-skill model evaluation,
which this repository does not publish.
"""

from __future__ import annotations

import hashlib
import json
import platform
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

RULE = "-" * 62


def out(line: str = "") -> None:
    print(line)


def git(*args: str) -> str:
    try:
        result = subprocess.run(
            ["git", "-C", str(ROOT), *args],
            capture_output=True,
            text=True,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return "unavailable"
    return result.stdout.strip()


def step(n: int, total: int, title: str) -> None:
    out()
    out(f"[{n}/{total}] {title}")


def main() -> int:
    failures: list[str] = []
    total = 4

    out("Quantum Reasoning Skill - quickstart verification")
    out(RULE)

    step(1, total, "Checkout identity")
    commit = git("rev-parse", "HEAD")
    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    skill_bytes = (ROOT / "SKILL.md").read_bytes()
    digest = hashlib.sha256(skill_bytes).hexdigest()
    out(f"    commit      : {commit}")
    out(f"    VERSION     : {version}")
    out(f"    SKILL.md    : {len(skill_bytes)} bytes  sha256:{digest[:16]}")
    out(f"    branch      : {git('rev-parse', '--abbrev-ref', 'HEAD')}")
    if commit == "unavailable":
        failures.append("cannot read git metadata (not a git checkout?)")
    if not version:
        failures.append("VERSION file is empty")

    step(2, total, "Agent Skill contract (SKILL.md)")
    text = skill_bytes.decode("utf-8")
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        failures.append("SKILL.md does not open with YAML front matter")
        out("    FAIL: missing front matter")
    else:
        end = next(i for i, line in enumerate(lines[1:], start=1) if line.strip() == "---")
        fields: dict[str, str] = {}
        for line in lines[1:end]:
            if ":" in line:
                key, value = line.split(":", 1)
                fields[key.strip()] = value.strip()
        name = fields.get("name", "")
        description = fields.get("description", "")
        out(f"    name        : {name}")
        out(f"    description : {len(description)} chars")
        out(f"    body        : {len(lines) - end - 1} lines")
        if name != "quantum-reasoning":
            failures.append(f"SKILL.md name is {name!r}, expected 'quantum-reasoning'")
        if not description:
            failures.append("SKILL.md has an empty description")
        if len(description) > 1024:
            failures.append("SKILL.md description exceeds the 1024-char skill limit")
        out("    status      : front matter parses and is host-ready")

    step(3, total, "Reference controller (reference/branch_controller.py)")
    from reference.branch_controller import (  # noqa: PLC0415
        Branch,
        BranchMetrics,
        collapse_decision,
        recommended_width,
        uncertainty_from_branches,
        update_branch_state,
    )

    out("    scenario: 'should we migrate our monolith to microservices?'")
    branches = [
        Branch(
            branch_id="strangler-fig-incremental",
            metrics=BranchMetrics(
                evidence=0.72,
                verification=0.66,
                independence=0.81,
                information_gain=0.55,
                contradiction=0.08,
                unresolved_assumptions=0.30,
                normalized_cost=0.35,
            ),
        ),
        Branch(
            branch_id="big-bang-rewrite",
            metrics=BranchMetrics(
                evidence=0.30,
                verification=0.22,
                independence=0.60,
                information_gain=0.40,
                contradiction=0.91,
                unresolved_assumptions=0.55,
                normalized_cost=0.70,
            ),
        ),
        Branch(
            branch_id="modular-monolith",
            metrics=BranchMetrics(
                evidence=0.55,
                verification=0.48,
                independence=0.74,
                information_gain=0.62,
                contradiction=0.10,
                unresolved_assumptions=0.35,
                normalized_cost=0.25,
            ),
        ),
        Branch(
            branch_id="feature-flag-carveout",
            metrics=BranchMetrics(
                evidence=0.20,
                verification=0.18,
                independence=0.55,
                information_gain=0.30,
                contradiction=0.05,
                unresolved_assumptions=0.60,
                normalized_cost=0.15,
            ),
        ),
    ]
    classified = [update_branch_state(branch) for branch in branches]
    for branch in classified:
        out(f"      {branch.branch_id:<26} {branch.state.value}")

    survivors = [b for b in classified if b.state.value != "rejected"]
    uncertainty = uncertainty_from_branches(classified)
    low, high = recommended_width(uncertainty)
    out(f"    uncertainty : {uncertainty:.4f}")
    out(f"    next width  : {low}-{high} branches (high uncertainty -> widen)")

    can_collapse, reason, leader = collapse_decision(classified)
    out(f"    leader      : {leader.branch_id if leader else 'none'}")
    out(f"    collapse    : {'ALLOWED' if can_collapse else 'BLOCKED'} - {reason}")
    if can_collapse:
        out("    note        : a collapse here would still not prove the skill helps;")
        out("                 it only means the reference thresholds were met.")

    dormant = next(b for b in classified if b.branch_id == "feature-flag-carveout")
    if dormant.state.value != "dormant":
        failures.append("expected feature-flag-carveout to become dormant")
    revived = Branch(
        branch_id=dormant.branch_id,
        metrics=BranchMetrics(
            evidence=0.45,
            verification=0.18,
            independence=0.55,
            information_gain=0.30,
            contradiction=0.05,
            unresolved_assumptions=0.60,
            normalized_cost=0.15,
        ),
        state=dormant.state,
        previous_metrics=dormant.metrics,
    )
    revived = update_branch_state(revived)
    out(f"    revival     : {dormant.branch_id} -> {revived.state.value} "
        f"(evidence +0.25 >= 0.15)")
    if revived.state.value != "active":
        failures.append("expected feature-flag-carveout to revive")
    out(f"    surviving   : {len(survivors)} branches")

    step(4, total, "Benchmark evaluator smoke run - SYNTHETIC PLACEHOLDER ROWS")
    out("    No language model is called. Baseline and skill rows below are")
    out("    byte-identical placeholders that exist only to prove the harness runs.")
    out("    The resulting accuracy is NOT a measurement of this skill.")
    cases_path = ROOT / "benchmark" / "cases.jsonl"
    case_ids = [
        json.loads(line)["id"]
        for line in cases_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    rows = [
        json.dumps(
            {
                "case_id": case_id,
                "answer": "323",
                "tokens": 120,
                "tool_calls": 0,
                "latency_ms": 950,
            }
        )
        for case_id in case_ids
    ]
    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        baseline = tmpdir / "baseline.jsonl"
        skill = tmpdir / "skill.jsonl"
        baseline.write_text("\n".join(rows) + "\n", encoding="utf-8")
        skill.write_text("\n".join(rows) + "\n", encoding="utf-8")
        result = subprocess.run(
            [
                sys.executable,
                str(ROOT / "benchmark" / "evaluate.py"),
                "--cases", str(cases_path),
                "--baseline", str(baseline),
                "--skill", str(skill),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
    if result.returncode != 0:
        failures.append("benchmark/evaluate.py failed on placeholder rows")
        out(f"    FAIL: {result.stderr.strip()[:200]}")
    else:
        payload = json.loads(result.stdout)
        comparison = payload["comparison"]
        out(f"    cases       : {payload['skill']['cases_evaluated']} seed cases")
        out(f"    accuracy    : {payload['skill']['accuracy']:.4f} (both conditions)")
        out(f"    delta       : {comparison['accuracy_delta']:+.4f} accuracy, "
            f"{comparison['tokens_percent_change']:+.1f}% tokens")
        out("    reading     : 0.00 delta is the expected result for identical")
        out("                 placeholder rows. It is a harness check, not evidence.")

    out()
    out(RULE)
    out("Provenance for every number printed above")
    out(RULE)
    out("    script      : docs/quickstart.py")
    out(f"    skill ver   : {version}   (VERSION)")
    out(f"    commit      : {commit}")
    out(f"    platform    : {platform.system()} {platform.release()} "
        f"({platform.machine()})")
    out(f"    python      : {platform.python_version()} "
        f"({platform.python_implementation()})")
    out("    controller  : reference/branch_controller.py DEFAULT_THRESHOLDS")
    out("    benchmark   : benchmark/cases.jsonl + benchmark/evaluate.py")
    out()
    if failures:
        out(f"RESULT: FAIL ({len(failures)} problem(s))")
        for failure in failures:
            out(f"  - {failure}")
        return 1
    out("RESULT: PASS (structure verified; no performance claim implied)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
