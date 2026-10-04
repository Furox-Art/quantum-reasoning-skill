#!/usr/bin/env python3
"""Toolchain pin guard for the release build chain.

The failure this prevents
--------------------------
`twine` 6.x and earlier monkeypatch the metadata-version list at import time:
`twine/package.py` assigns ``_VALID_METADATA_VERSIONS`` a hardcoded list ending
at ``2.4``, *replacing* the list ``packaging`` would otherwise supply. A build
backend that legitimately emits ``Metadata-Version: 2.5`` therefore fails
validation with::

    InvalidDistribution: Invalid distribution metadata: '2.5' is not a valid
    metadata version

``twine`` 7.0.0 removed the hardcoded list and delegates to ``packaging``.

The risk is that the two pins drift apart. Bumping ``hatchling`` alone silently
breaks the release; downgrading ``twine`` alone does the same. So this asserts
the *relationship* between them rather than either value in isolation:

* every workflow that runs ``twine check`` must pin twine, and pin it to a
  version at or above the minimum;
* the build backend must emit a metadata version that minimum can parse;
* ``constraints.txt`` and ``pyproject.toml`` must agree with the workflows.

UNPINNED is treated as a failure, so forgetting the pin cannot pass silently.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import tomllib

ROOT = Path(__file__).resolve().parents[1]

#: Lowest twine that delegates metadata validation to `packaging` instead of
#: hardcoding the version list.
MIN_TWINE = (7, 0, 0)

#: Highest core-metadata version the pre-7.0 twine list contained. A backend
#: emitting anything above this needs twine >= 7.0.0.
LAST_HARDCODED_METADATA = (2, 4)

WORKFLOW_DIR = ROOT / ".github" / "workflows"

#: `<name>==x.y.z`, used for twine, hatchling and any other pinned tool.
PIN = re.compile(r"([A-Za-z0-9_.-]+)==(\d+)\.(\d+)\.(\d+)")
#: A `twine check` invocation, used to decide which workflows matter.
TWINE_CHECK = re.compile(r"twine\s+check\b")
#: Any pip install line in a workflow, to find the toolchain pins.
PIP_INSTALL = re.compile(r"pip\s+install\b[^\n]*")


def pin_for(requirement: str, name: str) -> tuple[int, int, int] | None:
    """Return the pinned version of ``name`` in a requirement string, or None."""
    match = re.search(rf"{re.escape(name)}==(\d+)\.(\d+)\.(\d+)", requirement)
    if match is None:
        return None
    return (int(match.group(1)), int(match.group(2)), int(match.group(3)))


class Failure(Exception):
    """A pin contract violation."""


def parse_version(text: str) -> tuple[int, int, int]:
    """Parse a dotted numeric version, tolerating a two-component form.

    Core-metadata versions are two-component (`2.5`), tool versions are three
    (`7.0.0`), so both are accepted and padded with a trailing zero.
    """
    parts = text.strip().split(".")
    if len(parts) not in (2, 3) or not all(part.isdigit() for part in parts):
        raise Failure(f"cannot parse version {text!r}")
    while len(parts) < 3:
        parts.append("0")
    return (int(parts[0]), int(parts[1]), int(parts[2]))


def build_backend_metadata_ceiling(pyproject: dict) -> tuple[int, int]:
    """Return the highest metadata version the pinned backend can emit.

    Measured rather than guessed: hatchling started emitting
    ``Metadata-Version: 2.5`` in the 1.32 series. The floor is what any
    supported backend emits; the ceiling tracks the pin.
    """
    requires = pyproject.get("build-system", {}).get("requires", [])
    hatchling = next((r for r in requires if r.startswith("hatchling")), None)
    if hatchling is None:
        raise Failure("pyproject.toml does not pin a hatchling build backend")

    version = pin_for(hatchling, "hatchling")
    if version is None:
        raise Failure(f"hatchling is not version-pinned in pyproject.toml: {hatchling!r}")

    # hatchling 1.32+ emits 2.5; 1.27 emits 2.4.
    return (2, 5) if version >= (1, 32, 0) else (2, 4)


def workflows_running_twine_check() -> list[Path]:
    return sorted(
        path
        for path in WORKFLOW_DIR.glob("*.yml")
        if TWINE_CHECK.search(path.read_text(encoding="utf-8"))
    )


def check_workflow_pins(min_twine: tuple[int, int, int]) -> list[str]:
    """Every workflow running `twine check` must pin twine >= min_twine."""
    problems: list[str] = []
    workflows = workflows_running_twine_check()
    if not workflows:
        problems.append("no workflow runs `twine check`; the guard would be vacuous")

    for path in workflows:
        text = path.read_text(encoding="utf-8")
        installs = [line for line in PIP_INSTALL.findall(text) if "twine" in line]
        if not installs:
            problems.append(f"{path.name}: runs `twine check` but never installs twine")
            continue
        for line in installs:
            version = pin_for(line, "twine")
            if version is None:
                problems.append(
                    f"{path.name}: twine is UNPINNED in a `twine check` workflow: "
                    f"{line.strip()} — treat UNPINNED as a failure"
                )
                continue
            if version < min_twine:
                problems.append(
                    f"{path.name}: pins twine=={'.'.join(map(str, version))} but "
                    f">= {'.'.join(map(str, min_twine))} is required to parse the "
                    f"emitted metadata version"
                )
    return problems


def check_declared_pins(pyproject: dict, min_twine: tuple[int, int, int]) -> list[str]:
    """pyproject's dev group and constraints.txt must agree with the workflows."""
    problems: list[str] = []
    dev = pyproject.get("dependency-groups", {}).get("dev", [])
    twine_dev = next((d for d in dev if d.startswith("twine")), None)
    if twine_dev is None:
        problems.append("pyproject.toml dev group does not pin twine")
    else:
        version = pin_for(twine_dev, "twine")
        if version is None:
            problems.append(f"pyproject.toml dev group leaves twine unpinned: {twine_dev!r}")
        elif version < min_twine:
            problems.append(
                f"pyproject.toml dev group pins twine=={'.'.join(map(str, version))}, "
                f"below {'.'.join(map(str, min_twine))}"
            )

    constraints = ROOT / "constraints.txt"
    if not constraints.is_file():
        problems.append("constraints.txt is missing")
        return problems
    text = constraints.read_text(encoding="utf-8")
    version = pin_for(text, "twine")
    if version is None:
        problems.append("constraints.txt does not pin twine")
    elif version < min_twine:
        problems.append(
            f"constraints.txt pins twine=={'.'.join(map(str, version))}, "
            f"below {'.'.join(map(str, min_twine))}"
        )
    return problems


def check_metadata_is_parseable(
    pyproject: dict, min_twine: tuple[int, int, int], measured: str | None
) -> list[str]:
    """The backend's metadata version must be one the pinned twine can parse."""
    ceiling = build_backend_metadata_ceiling(pyproject)
    problems: list[str] = []

    # A measured value is the strongest evidence available: use it directly.
    effective = parse_version(measured)[:2] if measured else ceiling
    if measured and effective > ceiling:  # pragma: no cover - guards bad input
        problems.append(
            f"measured Metadata-Version {measured} exceeds what the pinned backend "
            f"can emit (ceiling {'.'.join(map(str, ceiling))})"
        )

    # This is the sibling repo's exact failure: twine below 7.0.0 replaces
    # packaging's metadata-version list with a hardcoded one ending at 2.4, so a
    # backend emitting anything above 2.4 fails `twine check` on valid artifacts.
    if min_twine < MIN_TWINE and effective > LAST_HARDCODED_METADATA:
        problems.append(
            f"backend emits Metadata-Version {'.'.join(map(str, effective))}, which twine "
            f"{'.'.join(map(str, min_twine))} cannot parse: twine below 7.0.0 replaces "
            f"packaging's metadata-version list with a hardcoded one ending at "
            f"{'.'.join(map(str, LAST_HARDCODED_METADATA))}. Require twine >= "
            f"{'.'.join(map(str, MIN_TWINE))}."
        )
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="check_toolchain_pins",
        description=(
            "Assert every `twine check` workflow pins twine new enough to parse the "
            "metadata version the pinned build backend emits. UNPINNED is a failure."
        ),
    )
    parser.add_argument(
        "--min-twine",
        default=".".join(map(str, MIN_TWINE)),
        help="minimum acceptable twine version (default: 7.0.0)",
    )
    parser.add_argument(
        "--metadata-version",
        help="optionally pass the measured Metadata-Version of the built artifacts",
    )
    args = parser.parse_args(argv)

    try:
        min_twine = parse_version(args.min_twine)
        pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        ceiling = build_backend_metadata_ceiling(pyproject)

        problems: list[str] = []
        problems.extend(check_workflow_pins(min_twine))
        problems.extend(check_declared_pins(pyproject, min_twine))
        problems.extend(check_metadata_is_parseable(pyproject, min_twine, args.metadata_version))
    except Failure as exc:
        print(f"::error::{exc}", file=sys.stderr)
        return 2

    print(f"required twine minimum : {'.'.join(map(str, min_twine))}")
    print(f"pinned build backend emits metadata up to {'.'.join(map(str, ceiling))}")
    print(f"workflows running twine check: {len(workflows_running_twine_check())}")

    if problems:
        print("\ntoolchain pin contract FAILED:", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        return 1

    print(
        "toolchain pin contract satisfied: every `twine check` workflow pins twine "
        f">= {'.'.join(map(str, min_twine))} (UNPINNED would fail)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
