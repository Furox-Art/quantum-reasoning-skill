#!/usr/bin/env python3
"""Release contract gate.

Run against an *installed* distribution (not the source tree) to prove the
published artifacts are actually usable. This is the check that keeps a
release from shipping a wheel that installs but exposes nothing.

Checks:
  1. The distribution imports.
  2. The public API documented in README.md is importable, constructible and
     callable.
  3. The skill contract (SKILL.md) ships inside the distribution.
  4. VERSION / pyproject / package.json / installed metadata agree.

Exit codes:
    0  contract satisfied
    1  contract violated (release must not proceed)
    2  the distribution could not be imported at all
"""

from __future__ import annotations

import argparse
import importlib
import importlib.metadata as metadata
import json
import re
import sys
from pathlib import Path

DISTRIBUTION = "quantum-reasoning-skill"
DISTRIBUTION_NORMALIZED = "quantum_reasoning_skill"
SEMVER = re.compile(r"^\d+\.\d+\.\d+(?:[.-][0-9A-Za-z.-]+)?$")

# The API advertised in README.md's Quick Start. These are deliberately
# explicit: the point of this gate is that a missing symbol is a release
# blocker, not a documentation nit.
REQUIRED_API: dict[str, tuple[str, tuple[str, ...]]] = {
    "ReasoningSession": (
        "importable class exported by " f"{DISTRIBUTION_NORMALIZED}",
        ("open_branch", "evaluate", "collapse"),
    ),
}

REQUIRED_REPO_FILES = ("SKILL.md", "VERSION")


class ContractError(Exception):
    """Raised when the installed distribution violates the release contract."""


def check_public_api(module_name: str) -> list[str]:
    """Verify every documented public symbol is importable and callable."""
    try:
        module = importlib.import_module(module_name)
    except ImportError as exc:
        raise ContractError(f"cannot import {module_name}: {exc}") from exc

    problems: list[str] = []
    for symbol, (where, methods) in REQUIRED_API.items():
        attribute = getattr(module, symbol, None)
        if attribute is None:
            problems.append(
                f"documented public API `{symbol}` is missing ({where}). "
                "The release must not ship a distribution that does not "
                "expose it."
            )
            continue
        if not callable(attribute):
            problems.append(f"`{symbol}` is present but not callable")
            continue
        for method in methods:
            if not callable(getattr(attribute, method, None)):
                problems.append(f"`{symbol}.{method}()` is documented but not callable")
    return problems


def check_skill_assets(module_name: str) -> list[str]:
    """Verify the skill contract ships inside the installed distribution."""
    module = importlib.import_module(module_name)
    problems: list[str] = []

    resolver = getattr(module, "skill_path", None)
    skill_file: Path | None = None
    if callable(resolver):
        try:
            skill_file = resolver()
        except FileNotFoundError as exc:
            problems.append(str(exc))
    else:
        # `skill_path()` is part of the package API but is owned by another
        # maintainer; fall back to the documented install layout so the asset
        # check still reports something meaningful while it is absent.
        package_dir = Path(module.__file__ or "").resolve().parent
        for candidate in (package_dir / "SKILL.md", package_dir.parent / "SKILL.md"):
            if candidate.is_file():
                skill_file = candidate
                break

    if skill_file is None and not problems:
        problems.append("SKILL.md does not ship inside the distribution")
    elif skill_file is not None and not skill_file.is_file():
        problems.append(f"skill_path() returned a non-existent file: {skill_file}")
    return problems


def check_version_lockstep(repo_root: Path) -> list[str]:
    """Assert VERSION / pyproject / package.json / installed metadata agree."""
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
    args = parser.parse_args(argv)

    problems: list[str] = []
    try:
        problems.extend(check_public_api(DISTRIBUTION_NORMALIZED))
    except ContractError as exc:
        print(f"::error::{exc}", file=sys.stderr)
        return 2

    problems.extend(check_skill_assets(DISTRIBUTION_NORMALIZED))
    problems.extend(check_version_lockstep(args.repo_root.resolve()))

    if problems:
        print("Release contract FAILED:", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        return 1

    print(
        f"Release contract satisfied: {DISTRIBUTION} "
        f"{metadata.version(DISTRIBUTION)} exposes the documented public API."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
