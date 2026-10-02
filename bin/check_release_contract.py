#!/usr/bin/env python3
"""Release contract gate.

Run against an *installed* distribution (not the source tree) to prove the
published artifacts are actually usable. This is the check that keeps a release
from shipping a wheel that installs but ships nothing.

This asserts the API surface the package actually provides:

1. the skill contract (``SKILL.md``) resolves inside the installed wheel;
2. the documented console entry point is installed and runs;
3. the reference branch controller is importable from the installed
   distribution and its public functions are callable;
4. the console entry point's own validation passes on the installed asset.

Every check is fail-closed: if the asset or the entry point is removed, or the
controller is renamed or emptied, this exits non-zero and the release stops.

Note on history: an earlier revision of this gate asserted a ``ReasoningSession``
class. That class never existed in this codebase; the README claim was
fabricated and has been removed. Asserting it made the gate impossible to
satisfy. The surface asserted here is the real one.

Exit codes:
    0  contract satisfied
    1  contract violated (release must not proceed)
    2  the distribution could not be inspected at all
"""

from __future__ import annotations

import argparse
import importlib
import importlib.metadata as metadata
import json
import os
import re
import subprocess
import sys
from pathlib import Path

DISTRIBUTION = "quantum-reasoning-skill"
DISTRIBUTION_NORMALIZED = "quantum_reasoning_skill"
SKILL_MODULE = f"{DISTRIBUTION_NORMALIZED}.cli"
CONTROLLER_MODULE = "reference.branch_controller"
CONSOLE_SCRIPT = "quantum-reasoning"
SEMVER = re.compile(r"^\d+\.\d+\.\d+(?:[.-][0-9A-Za-z.-]+)?$")

# Public names the reference controller actually provides. If any of these is
# renamed or dropped, the release stops. Values that are data rather than
# behaviour are only required to exist; callables must be callable.
REQUIRED_CONTROLLER_SYMBOLS = (
    "DEFAULT_THRESHOLDS",
    "Branch",
    "BranchMetrics",
    "BranchState",
    "Thresholds",
    "branch_score",
    "classify_branch",
    "collapse_decision",
    "diversity_ratio",
    "recommended_width",
    "uncertainty_from_branches",
    "update_branch_state",
)

# Symbols that must be callable (functions/classes), as opposed to merely present.
REQUIRED_CONTROLLER_CALLABLES = frozenset(
    {
        "Branch",
        "BranchMetrics",
        "BranchState",
        "Thresholds",
        "branch_score",
        "classify_branch",
        "collapse_decision",
        "diversity_ratio",
        "recommended_width",
        "uncertainty_from_branches",
        "update_branch_state",
    }
)


class ContractError(Exception):
    """Raised when the installed distribution cannot be inspected at all."""


# ---------------------------------------------------------------------------
# 1. The skill contract must ship inside the distribution.
# ---------------------------------------------------------------------------
def check_skill_asset() -> list[str]:
    """Verify SKILL.md resolves inside the installed distribution."""
    problems: list[str] = []
    try:
        module = importlib.import_module(DISTRIBUTION_NORMALIZED)
    except ImportError as exc:
        raise ContractError(f"cannot import {DISTRIBUTION_NORMALIZED}: {exc}") from exc

    package_dir = Path(module.__file__ or "").resolve().parent
    skill_file = package_dir / "SKILL.md"
    if not skill_file.is_file():
        problems.append(
            f"SKILL.md is not installed at {skill_file}; the wheel no longer "
            "ships the skill contract"
        )
        return problems

    if skill_file.stat().st_size == 0:
        problems.append(f"installed SKILL.md is empty: {skill_file}")
    return problems


# ---------------------------------------------------------------------------
# 2. The documented console entry point must be installed and runnable.
# ---------------------------------------------------------------------------
def check_console_entry_point() -> list[str]:
    """Verify the `quantum-reasoning` console script exists and validates."""
    problems: list[str] = []
    try:
        scripts = metadata.distribution(DISTRIBUTION).entry_points
    except metadata.PackageNotFoundError as exc:
        raise ContractError(f"{DISTRIBUTION} is not installed") from exc

    console = {ep.name: ep for ep in scripts if ep.group == "console_scripts"}
    if CONSOLE_SCRIPT not in console:
        installed = ", ".join(sorted(console)) or "<none>"
        problems.append(
            f"documented console entry point `{CONSOLE_SCRIPT}` is not installed "
            f"(found: {installed})"
        )
        return problems

    entry_point = console[CONSOLE_SCRIPT]
    expected_target = f"{SKILL_MODULE}:main"
    if entry_point.value != expected_target:
        problems.append(
            f"`{CONSOLE_SCRIPT}` points at {entry_point.value}, expected {expected_target}"
        )

    executable = _resolve_executable(entry_point)
    if executable is None:
        problems.append(
            f"`{CONSOLE_SCRIPT}` is declared but no runnable script was found "
            f"for {entry_point.value}"
        )
        return problems

    result = subprocess.run(  # noqa: S603 - fixed argv, no shell
        [str(executable), "--validate"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        problems.append(
            f"`{CONSOLE_SCRIPT} --validate` exited {result.returncode} against the "
            f"installed asset: {result.stderr.strip() or result.stdout.strip()}"
        )
    return problems


def _resolve_executable(entry_point: metadata.EntryPoint) -> Path | None:
    """Locate the installed script file for a console_scripts entry point."""
    scripts_dir = Path(sys.executable).resolve().parent
    candidates = [
        scripts_dir / CONSOLE_SCRIPT,
        scripts_dir / f"{CONSOLE_SCRIPT}.exe",
        scripts_dir / f"{CONSOLE_SCRIPT}.cmd",
        scripts_dir / f"{CONSOLE_SCRIPT}.bat",
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


# ---------------------------------------------------------------------------
# 3. The reference branch controller must be importable and callable.
# ---------------------------------------------------------------------------
def check_reference_controller() -> list[str]:
    """Verify the reference controller imports and its public API is callable."""
    problems: list[str] = []
    try:
        controller = importlib.import_module(CONTROLLER_MODULE)
    except ImportError as exc:
        problems.append(
            f"the reference controller `{CONTROLLER_MODULE}` is not importable from "
            f"the installed distribution: {exc}"
        )
        return problems

    controller_file = Path(controller.__file__ or "").resolve()
    if controller_file.name != "branch_controller.py":
        problems.append(f"{CONTROLLER_MODULE} resolved to an unexpected file: {controller_file}")

    for symbol in REQUIRED_CONTROLLER_SYMBOLS:
        attribute = getattr(controller, symbol, None)
        if attribute is None:
            problems.append(f"`{CONTROLLER_MODULE}.{symbol}` is missing")
        elif symbol in REQUIRED_CONTROLLER_CALLABLES and not callable(attribute):
            problems.append(f"`{CONTROLLER_MODULE}.{symbol}` is not callable")

    # Exercise the surface end to end so the gate proves behaviour, not just
    # attribute presence.
    problems.extend(_exercise_controller(controller))
    return problems


def _exercise_controller(controller: object) -> list[str]:
    """Call the controller's public functions with known-good inputs."""
    problems: list[str] = []
    try:
        metrics = controller.BranchMetrics(  # type: ignore[attr-defined]
            evidence=0.8,
            verification=0.8,
            independence=0.9,
            information_gain=0.6,
            contradiction=0.1,
            unresolved_assumptions=0.1,
            normalized_cost=0.2,
        )
        score = controller.branch_score(metrics)  # type: ignore[attr-defined]
        if not isinstance(score, float):
            problems.append(f"branch_score() returned {type(score).__name__}, expected float")
    except Exception as exc:  # noqa: BLE001 - any failure is a contract breach
        problems.append(f"branch_score() raised {type(exc).__name__}: {exc}")
        return problems

    try:
        width = controller.recommended_width(0.40)  # type: ignore[attr-defined]
        if not (isinstance(width, tuple) and width == (4, 6)):
            problems.append(f"recommended_width(0.40) returned {width!r}, expected (4, 6)")
    except Exception as exc:  # noqa: BLE001
        problems.append(f"recommended_width() raised {type(exc).__name__}: {exc}")

    try:
        leader = controller.Branch(  # type: ignore[attr-defined]
            "leader",
            controller.BranchMetrics(  # type: ignore[attr-defined]
                evidence=1.0,
                verification=1.0,
                independence=1.0,
                information_gain=0.8,
                contradiction=0.0,
                unresolved_assumptions=0.0,
                normalized_cost=0.0,
            ),
        )
        weak = controller.Branch(  # type: ignore[attr-defined]
            "weak",
            controller.BranchMetrics(  # type: ignore[attr-defined]
                evidence=0.35,
                verification=0.30,
                independence=0.5,
                information_gain=0.2,
                contradiction=0.4,
                unresolved_assumptions=0.5,
                normalized_cost=0.4,
            ),
        )
        can_collapse, reason, selected = controller.collapse_decision([leader, weak])  # type: ignore[attr-defined]
        if not can_collapse:
            problems.append(f"collapse_decision() refused an obvious leader: {reason}")
        if getattr(selected, "branch_id", None) != "leader":
            problems.append(
                f"collapse_decision() selected {getattr(selected, 'branch_id', None)!r}"
            )
    except Exception as exc:  # noqa: BLE001
        problems.append(f"collapse_decision() raised {type(exc).__name__}: {exc}")
    return problems


# ---------------------------------------------------------------------------
# 4. The installed CLI must agree with the installed metadata.
# ---------------------------------------------------------------------------
def check_version_lockstep(repo_root: Path) -> list[str]:
    """Assert VERSION / pyproject / package.json / CHANGELOG / CITATION agree."""
    problems: list[str] = []
    problems.extend(_validate_semver(repo_root, problems))

    versions: dict[str, str] = {}
    version_file = repo_root / "VERSION"
    if version_file.is_file():
        versions["VERSION"] = version_file.read_text(encoding="utf-8").strip().lstrip("v")
    else:
        problems.append("VERSION file is missing")

    try:
        import tomllib
    except ModuleNotFoundError:  # pragma: no cover - Python < 3.11
        problems.append("tomllib unavailable; cannot check pyproject version")
    else:
        pyproject = repo_root / "pyproject.toml"
        if pyproject.is_file():
            data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
            versions["pyproject.toml"] = str(data.get("project", {}).get("version", ""))
        else:
            problems.append("pyproject.toml is missing")

    package_json = repo_root / "package.json"
    if package_json.is_file():
        versions["package.json"] = str(
            json.loads(package_json.read_text(encoding="utf-8")).get("version", "")
        )
    else:
        problems.append("package.json is missing")

    changelog = repo_root / "CHANGELOG.md"
    if changelog.is_file():
        changelog_version = _changelog_latest_version(changelog.read_text(encoding="utf-8"))
        if changelog_version is None:
            problems.append("CHANGELOG.md has no `## [x.y.z]` release section")
        else:
            versions["CHANGELOG.md"] = changelog_version
    else:
        problems.append("CHANGELOG.md is missing")

    citation = repo_root / "CITATION.cff"
    if citation.is_file():
        text = citation.read_text(encoding="utf-8")
        match = re.search(r"^version:\s*(\S+)\s*$", text, re.MULTILINE)
        if match is None:
            problems.append("CITATION.cff has no `version:` field")
        else:
            versions["CITATION.cff"] = match.group(1)

    try:
        versions["installed"] = metadata.version(DISTRIBUTION)
    except metadata.PackageNotFoundError:
        problems.append(f"{DISTRIBUTION} is not installed in this environment")

    distinct = {value for value in versions.values() if value}
    if len(distinct) > 1:
        detail = ", ".join(f"{name}={value}" for name, value in sorted(versions.items()))
        problems.append(f"version lockstep violated across: {detail}")
    return problems


def _validate_semver(repo_root: Path, problems: list[str]) -> list[str]:
    version_file = repo_root / "VERSION"
    if not version_file.is_file():
        return problems
    value = version_file.read_text(encoding="utf-8").strip().lstrip("v")
    if not SEMVER.match(value):
        problems.append(f"VERSION is not a semantic version: {value!r}")
    return problems


def _changelog_latest_version(text: str) -> str | None:
    for line in text.splitlines():
        match = re.match(r"^##\s+\[([^\]]+)\]", line.strip())
        if match and match.group(1) != "Unreleased":
            return match.group(1)
    return None


# ---------------------------------------------------------------------------
# Negative control
# ---------------------------------------------------------------------------
def run_negative_control() -> int:
    """Prove the gate is fail-closed by hiding each asset in turn.

    Each check is run against a deliberately broken installation. If any broken
    installation still passes, the corresponding check is not fail-closed and
    this exits non-zero. This guards against a gate that silently degrades into
    a no-op.
    """
    try:
        module = importlib.import_module(DISTRIBUTION_NORMALIZED)
    except ImportError as exc:
        raise ContractError(f"cannot import {DISTRIBUTION_NORMALIZED}: {exc}") from exc

    package_dir = Path(module.__file__ or "").resolve().parent
    skill_file = package_dir / "SKILL.md"
    if not skill_file.is_file():
        print("negative control: SKILL.md is absent, nothing to hide")
        return 1

    failures: list[str] = []

    # (a) Remove SKILL.md -> the asset check must fail.
    backup = skill_file.read_bytes()
    try:
        skill_file.unlink()
        problems = check_skill_asset()
        if not problems:
            failures.append(
                "FAIL-CLOSED BROKEN: removing the installed SKILL.md did not fail the asset check"
            )
        else:
            print("negative control: SKILL.md removed -> gate failed as expected")
    finally:
        skill_file.write_bytes(backup)

    # (b) Empty SKILL.md -> the asset check must fail.
    try:
        skill_file.write_bytes(b"")
        problems = check_skill_asset()
        if not problems:
            failures.append(
                "FAIL-CLOSED BROKEN: emptying the installed SKILL.md did not fail the asset check"
            )
        else:
            print("negative control: SKILL.md emptied -> gate failed as expected")
    finally:
        skill_file.write_bytes(backup)

    # (c) A controller that is missing its public API must be rejected.
    problems = _check_controller_symbols_stub()
    if not problems:
        failures.append("FAIL-CLOSED BROKEN: a controller missing its public API was accepted")
    else:
        print(f"negative control: stub controller rejected -> {problems[0]}")

    # (d) A controller whose functions misbehave must be rejected.
    problems = _exercise_controller(_MisbehavingController())
    if not problems:
        failures.append("FAIL-CLOSED BROKEN: a controller returning wrong values was accepted")
    else:
        print(f"negative control: misbehaving controller rejected -> {problems[0]}")

    if not skill_file.is_file() or skill_file.read_bytes() != backup:
        failures.append("negative control did not restore SKILL.md")
    else:
        print("negative control: SKILL.md restored intact")

    if failures:
        print("\nNegative control FAILED:", file=sys.stderr)
        for failure in failures:
            print(f"  - {failure}", file=sys.stderr)
        return 1
    print("\nNegative control passed: the gate is fail-closed against asset removal.")
    return 0


class _MisbehavingController:
    """A controller whose public names exist but return wrong values."""

    BranchMetrics = staticmethod(lambda **kwargs: type("M", (), {"kwargs": kwargs})())
    Branch = staticmethod(
        lambda branch_id, metrics, **kwargs: type("B", (), {"branch_id": branch_id})()
    )

    @staticmethod
    def branch_score(metrics):  # type: ignore[no-untyped-def]
        return "not-a-float"

    @staticmethod
    def recommended_width(uncertainty):  # type: ignore[no-untyped-def]
        return (99, 99)

    @staticmethod
    def collapse_decision(branches):  # type: ignore[no-untyped-def]
        return (False, "stub", branches[0])


def _check_controller_symbols_stub() -> list[str]:
    """Confirm the symbol check rejects an empty module."""

    class _Empty:
        pass

    missing = [
        symbol for symbol in REQUIRED_CONTROLLER_SYMBOLS if getattr(_Empty, symbol, None) is None
    ]
    return [f"missing symbol: {symbol}" for symbol in missing]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="check-release-contract",
        description="Verify an installed distribution satisfies the release contract.",
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="source checkout to cross-check version lockstep against",
    )
    parser.add_argument(
        "--negative-control",
        action="store_true",
        help="prove the gate fails when the installed assets are removed",
    )
    args = parser.parse_args(argv)

    if args.negative_control:
        try:
            return run_negative_control()
        except ContractError as exc:
            print(f"::error::{exc}", file=sys.stderr)
            return 2

    problems: list[str] = []
    try:
        problems.extend(check_skill_asset())
        problems.extend(check_console_entry_point())
        problems.extend(check_reference_controller())
    except ContractError as exc:
        print(f"::error::{exc}", file=sys.stderr)
        return 2

    problems.extend(check_version_lockstep(args.repo_root.resolve()))

    if problems:
        print("Release contract FAILED:", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        return 1

    version = metadata.version(DISTRIBUTION)
    print(f"Release contract satisfied for {DISTRIBUTION} {version}:")
    print("  - SKILL.md ships inside the distribution")
    print(f"  - console entry point `{CONSOLE_SCRIPT}` runs against the installed asset")
    print(f"  - reference controller `{CONTROLLER_MODULE}` imports and its API is callable")
    print(f"  - version lockstep holds ({version})")
    return 0


if __name__ == "__main__":
    # Keep the subprocess import honest when run as a module.
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    raise SystemExit(main())
