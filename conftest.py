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
#: of them to six decimals (``benchmark/falsification/run_suite.py`` writes
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
    try:
        import tomllib
    except ModuleNotFoundError:  # pragma: no cover - Python < 3.11
        import tomli as tomllib  # type: ignore[no-redef]
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    return str(data["project"]["version"])


def package_json_version() -> str:
    """Return the version declared in ``package.json``."""
    data = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
    return str(data["version"])


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
