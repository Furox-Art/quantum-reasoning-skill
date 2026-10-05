#!/usr/bin/env python3
"""Strict GitHub Actions workflow validation.

Why this exists
---------------
``.github/workflows/npm-publish.yml`` shipped to ``main`` with duplicate mapping
keys in a single step (``shell``, ``env`` and ``run`` each defined twice). GitHub
rejected the file at parse time, so ``gh workflow run npm-publish.yml`` returned
``HTTP 422 ... 'shell' is already defined`` and no manual publish could start at
all.

Two things let it through:

* ``yaml.safe_load`` accepts duplicate keys and keeps the last one silently. Every
  "does the YAML parse?" check in this repository used it, so the broken file
  passed them.
* no workflow ran a GitHub Actions *schema* check, so nothing rejected keys that
  are invalid in a step.

This module closes both holes:

1. :func:`strict_load` parses with a loader that **raises** on duplicate keys.
2. :func:`check_workflow_structure` enforces the structural rules that catch this
   class of defect independently of a schema: exactly one ``name``/``run``/``env``
   /``shell``/``uses``/``if``/``id``/``with``/``permissions``/``timeout-minutes``
   per step, and steps that carry ``run`` or ``uses`` rather than both.

It also runs every step shell body through ``bash -n`` where possible, so a
syntax error in a step is caught before it reaches the runner.

Usage::

    python bin/check_workflows.py            # validate every workflow
    python bin/check_workflows.py --verbose  # list what each workflow declares
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_DIR = ROOT / ".github" / "workflows"


class DuplicateKeyError(Exception):
    """A mapping defined the same key twice."""


class StrictLoader(yaml.SafeLoader):
    """A ``SafeLoader`` that refuses duplicate mapping keys.

    ``yaml.SafeLoader`` resolves duplicates silently, keeping the last value, so
    a step with two ``run:`` blocks parses without complaint and the first block
    is discarded. That is exactly how an invalid workflow reached ``main``. This
    loader instead constructs mappings through a constructor that compares
    ``_keys`` against the keys already seen.
    """


def _construct_mapping(loader: StrictLoader, node: yaml.Node, deep: bool = False) -> dict[str, Any]:
    loader.flatten_mapping(node)
    mapping: dict[str, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in mapping:
            raise DuplicateKeyError(
                f"{key!r} is already defined (line {key_node.start_mark.line + 1})"
            )
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


StrictLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_mapping)


def strict_load(text: str, *, source: str = "<workflow>") -> Any:
    """Parse YAML, raising :class:`DuplicateKeyError` on any duplicate key."""
    try:
        return yaml.load(text, Loader=StrictLoader)  # noqa: S506 - StrictLoader is SafeLoader
    except yaml.YAMLError as exc:
        raise DuplicateKeyError(f"{source}: {exc}") from exc


#: Keys that a single step may define at most once.
SINGLETON_STEP_KEYS = (
    "name",
    "id",
    "if",
    "uses",
    "run",
    "shell",
    "env",
    "with",
    "timeout-minutes",
    "continue-on-error",
    "working-directory",
)

#: Keys that may only appear once at the top level of a workflow.
SINGLETON_WORKFLOW_KEYS = ("name", "on", "env", "defaults", "concurrency", "permissions", "jobs")


def _raw_key_counts(text: str) -> list[tuple[str, int, int]]:
    """Return ``(key, count, first_line)`` for step-level keys in a raw document.

    Parsing is not enough on its own: a duplicate is already a parse error by the
    time the structure is available. Counting occurrences of the raw key text
    lets this report *where* the duplicate is, per step block, which the message
    from the loader alone does not.
    """
    findings: list[tuple[str, int, int]] = []
    current_step: list[tuple[str, int]] = []
    step_start = 0
    for number, line in enumerate(text.replace("\r\n", "\n").splitlines(), start=1):
        step_match = re.match(r"^(\s*)-\s+(?:name|uses|id|run|env|shell|if)\b", line)
        if step_match:
            if current_step:
                findings.extend(_duplicates_in(current_step, step_start))
            current_step = []
            step_start = number
        if current_step is not None and line.strip():
            key_match = re.match(r"^\s{6,}([A-Za-z_][A-Za-z0-9_-]*):", line)
            if key_match:
                current_step.append((key_match.group(1), number))
    if current_step:
        findings.extend(_duplicates_in(current_step, step_start))
    return findings


def _duplicates_in(pairs: list[tuple[str, int]], step_start: int) -> list[tuple[str, int, int]]:
    seen: dict[str, int] = {}
    out: list[tuple[str, int, int]] = []
    for key, number in pairs:
        if key in SINGLETON_STEP_KEYS:
            if key in seen:
                out.append((key, number, seen[key]))
            else:
                seen[key] = number
    return out


def check_workflow_structure(path: Path) -> list[str]:
    """Validate one workflow. Returns a list of problems (empty when valid)."""
    problems: list[str] = []
    relative = path.relative_to(ROOT).as_posix()
    text = path.read_text(encoding="utf-8")

    # 1. Duplicate keys must be rejected, not silently resolved.
    try:
        document = strict_load(text, source=relative)
    except DuplicateKeyError as exc:
        problems.append(f"{relative}: duplicate mapping key: {exc}")
        document = None

    # 2. Independently of parsing, count raw step keys so the message names the
    #    step and both line numbers even when parsing aborted.
    for key, second, first in _raw_key_counts(text):
        problems.append(
            f"{relative}: step defines {key!r} twice (lines {first} and {second}); "
            "GitHub rejects the whole workflow and no job can run"
        )

    if document is None:
        return problems

    # 3. Structural rules a schema check would otherwise catch.
    if not isinstance(document, dict):
        problems.append(f"{relative}: workflow is not a mapping")
        return problems

    for key in SINGLETON_WORKFLOW_KEYS:
        if text.count(f"\n{key}:") > 1:
            problems.append(f"{relative}: workflow defines {key!r} more than once")

    jobs = document.get("jobs")
    if not isinstance(jobs, dict) or not jobs:
        problems.append(f"{relative}: no jobs defined")
        return problems

    for job_name, job in jobs.items():
        if not isinstance(job, dict):
            problems.append(f"{relative}: job {job_name!r} is not a mapping")
            continue
        steps = job.get("steps")
        if steps is None:
            continue
        if not isinstance(steps, list):
            problems.append(f"{relative}: job {job_name!r} steps is not a list")
            continue
        for index, step in enumerate(steps):
            if not isinstance(step, dict):
                problems.append(f"{relative}: job {job_name!r} step {index} is not a mapping")
                continue
            label = step.get("name") or step.get("uses") or f"step {index}"
            if "run" in step and "uses" in step:
                problems.append(
                    f"{relative}: job {job_name!r} step {label!r} has both 'run' and 'uses'; "
                    "a step does one or the other"
                )
            if "run" not in step and "uses" not in step:
                problems.append(
                    f"{relative}: job {job_name!r} step {label!r} has neither 'run' nor 'uses'"
                )
            problems.extend(_check_bash_syntax(relative, job_name, label, step.get("run")))

    return problems


def _check_bash_syntax(relative: str, job_name: str, label: Any, run: Any) -> list[str]:
    """Run ``bash -n`` over a step body when it looks like POSIX shell."""
    if not isinstance(run, str) or not run.strip():
        return []
    if "\r" in run:
        return []
    if shutil.which("bash") is None:  # pragma: no cover - bash ships on every CI runner
        return []
    proc = subprocess.run(
        ["bash", "-n"],
        input=run.encode("utf-8"),
        capture_output=True,
        check=False,
    )
    if proc.returncode == 0:
        return []
    detail = proc.stderr.decode("utf-8", "replace").strip().splitlines()
    return [
        f"{relative}: job {job_name!r} step {label!r} is not valid bash: "
        + (detail[0] if detail else "syntax error")
    ]


def workflow_files() -> list[Path]:
    return sorted(WORKFLOW_DIR.glob("*.yml")) + sorted(WORKFLOW_DIR.glob("*.yaml"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="check_workflows",
        description=(
            "Validate every GitHub Actions workflow: duplicate keys are an error, "
            "step structure is checked, and step shell bodies must parse."
        ),
    )
    parser.add_argument("--verbose", action="store_true", help="list each workflow checked")
    args = parser.parse_args(argv)

    files = workflow_files()
    if not files:
        print("::error::no workflow files found", file=sys.stderr)
        return 2

    if args.verbose:
        for path in files:
            print(f"checking {path.relative_to(ROOT).as_posix()}")

    problems: list[str] = []
    for path in files:
        problems.extend(check_workflow_structure(path))

    if problems:
        print("\nworkflow validation FAILED:", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        return 1

    print(
        f"workflow validation passed: {len(files)} workflow(s) parse with a "
        f"duplicate-rejecting loader and every step is well-formed."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
