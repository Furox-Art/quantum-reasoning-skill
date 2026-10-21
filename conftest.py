"""Shared CI helpers.

These assertions are deliberately independent of the repository layout so that
they keep working while the library is being developed. They live in the root
``conftest.py`` because they are used by both pytest and the standalone CI
scripts.
"""

from __future__ import annotations

import json
import re
import sys
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SEMVER = re.compile(r"^\d+\.\d+\.\d+(?:[.-][0-9A-Za-z.-]+)?$")
CHANGELOG_VERSION = re.compile(r"^##\s+\[([^\]]+)\]", re.MULTILINE)

#: The one numeric tolerance this repository compares floats with.
#:
#: Why a single number instead of `assertEqual` or `assertAlmostEqual`: the
#: metrics are floating-point arithmetic, and the committed artifacts round some
#: of them to six decimals (``quantum_reasoning_skill/benchmark/falsification/run_suite.py`` writes
#: ``round(value, 6)`` for `brier`, `latency_ms`, `leader_score` and
#: `probabilities`). Measured on one machine, the stored and freshly recomputed
#: `brier` differ by up to 4.9e-7 and the stored and fresh reliability-bin
#: `truth_probability` by up to 3.4e-16. Exact equality therefore rejects
#: artifacts that are correct, while `assertAlmostEqual`'s default of seven
#: decimal places is a third, undocumented tolerance. One helper, one number:
#: large enough to absorb the six-decimal rounding, small enough that no two
#: distinct published metrics are within it.
NUMERIC_TOLERANCE = 1e-6


def repo_version() -> str:
    """Return the canonical repository version from the ``VERSION`` file."""
    return (ROOT / "VERSION").read_text(encoding="utf-8").strip().lstrip("v")


def pyproject_version() -> str:
    """Return the version declared in ``pyproject.toml``."""
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    try:
        import tomllib
    except ModuleNotFoundError:  # pragma: no cover - Python < 3.11
        try:
            import tomli as tomllib  # type: ignore[no-redef]
        except ModuleNotFoundError:  # pragma: no cover - bare 3.10 CI job
            # The 3.10 behavioral job installs nothing beyond the stdlib, so
            # neither parser is available. Read the one field this helper
            # promises, from the [project] table only, rather than skipping
            # the lockstep check on that interpreter.
            project = text.split("[project]", 1)[1].split("\n[", 1)[0]
            match = re.search(r'^version = "([^"]+)"$', project, re.MULTILINE)
            if match is None:
                raise ValueError("pyproject.toml has no [project] version") from None
            return match.group(1)
    data = tomllib.loads(text)
    return str(data["project"]["version"])


def package_json_version() -> str:
    """Return the version declared in ``package.json``."""
    data = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
    return str(data["version"])


def codemeta_version() -> str | None:
    """Return ``codemeta.json``'s version, or ``None`` when it has no field."""
    path = ROOT / "codemeta.json"
    if not path.is_file():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    value = data.get("version")
    return str(value) if value else None


def skill_front_matter_version() -> str | None:
    """Return the version in ``SKILL.md``'s YAML front matter, if present."""
    lines = (ROOT / "SKILL.md").read_text(encoding="utf-8").splitlines()
    if not lines or lines[0].strip() != "---":
        return None
    try:
        end = next(i for i, line in enumerate(lines[1:], start=1) if line.strip() == "---")
    except StopIteration:
        return None
    for line in lines[1:end]:
        match = re.match(r"^\s+version:\s*[\"']?([^\"'\s]+)", line)
        if match:
            return match.group(1)
    return None


def changelog_version() -> str | None:
    """Return the most recent released version recorded in ``CHANGELOG.md``."""
    text = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    for match in CHANGELOG_VERSION.finditer(text):
        if match.group(1) != "Unreleased":
            return match.group(1)
    return None


def load_script(name: str, relative: str):
    """Import a repository script that is not part of the installed package."""
    spec = spec_from_file_location(name, ROOT / relative)
    if spec is None or spec.loader is None:  # pragma: no cover - defensive
        raise ImportError(f"cannot load {relative}")
    module = module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def is_close(
    actual: float | None,
    expected: float | None,
    *,
    tolerance: float = NUMERIC_TOLERANCE,
) -> bool:
    """Absolute-tolerance comparison used for every numeric equality here.

    ``None`` means "not measured", so two absent values agree and an absent one
    never agrees with a measured one.
    """
    if actual is None or expected is None:
        return actual is expected
    return abs(actual - expected) <= tolerance


def assert_close(
    actual: float | None,
    expected: float | None,
    *,
    tolerance: float = NUMERIC_TOLERANCE,
    message: str = "",
) -> None:
    """Raise :class:`AssertionError` unless the values are within ``tolerance``."""
    if is_close(actual, expected, tolerance=tolerance):
        return
    if actual is None or expected is None:
        detail = f"{actual!r} vs {expected!r}"
    else:
        detail = f"{actual!r} vs {expected!r} differ by {abs(actual - expected):.3g}"
    context = f" ({message})" if message else ""
    raise AssertionError(f"{detail} exceeds tolerance {tolerance:g}{context}")


def version_lockstep_failures() -> list[str]:
    """Return a list of version lockstep violations (empty when consistent)."""
    versions = {
        "VERSION": repo_version(),
        "pyproject.toml": pyproject_version(),
        "package.json": package_json_version(),
    }
    released = changelog_version()
    if released is None:
        failures = ["CHANGELOG.md has no `## [x.y.z]` release section"]
    else:
        versions["CHANGELOG.md"] = released
        failures = []

    citation = ROOT / "CITATION.cff"
    if citation.is_file():
        text = citation.read_text(encoding="utf-8")
        match = re.search(r"^version:\s*(\S+)\s*$", text, re.MULTILINE)
        if match is None:
            failures.append("CITATION.cff has no `version:` field")
        else:
            versions["CITATION.cff"] = match.group(1)

    distinct = set(versions.values())
    if len(distinct) > 1:
        detail = ", ".join(f"{name}={value}" for name, value in sorted(versions.items()))
        failures.append(f"version lockstep violated across: {detail}")

    canonical = versions["VERSION"]
    if not SEMVER.match(canonical):
        failures.append(f"VERSION is not a semantic version: {canonical!r}")
    return failures


def is_prerelease(version: str) -> bool:
    """True when a semantic version carries a prerelease suffix.

    Build metadata (``+...``) does not make a release a prerelease; only the
    ``-`` component does.
    """
    return bool(re.search(r"-[0-9A-Za-z.-]+(?:\+[0-9A-Za-z.-]+)?$", version))


def release_version_failures() -> list[str]:
    """Return violations across every version-bearing surface in the tree.

    :func:`version_lockstep_failures` covers the five surfaces every release
    job already checked (VERSION, pyproject.toml, package.json, CITATION.cff,
    CHANGELOG.md). The release metadata that ships beside them has two more:
    ``codemeta.json`` and ``SKILL.md``'s front-matter version. The package
    ``__init__.py`` deliberately carries no version, so there is nothing to
    compare there.
    """
    failures = version_lockstep_failures()
    canonical = repo_version()
    for name, value in (
        ("codemeta.json", codemeta_version()),
        ("SKILL.md metadata.version", skill_front_matter_version()),
    ):
        if not value:
            failures.append(f"{name} has no version field")
        elif value != canonical:
            failures.append(f"{name} ({value}) does not match VERSION ({canonical})")
    return failures
