"""Benchmark tooling for the Quantum Reasoning Skill.

This directory is a real package rather than a loose folder of scripts so that
its modules are always imported as ``quantum_reasoning_skill.benchmark.<module>``.
Intra-package imports are absolute and package-qualified, which means a stray
``evaluate.py`` in the current working directory, on ``PYTHONPATH``, or shipped
by an unrelated third-party distribution can no longer shadow
:mod:`quantum_reasoning_skill.benchmark.evaluate`.

Both modules also remain runnable as plain scripts; they install the checkout
root (three levels above this file) at the front of ``sys.path`` and then import
the package-qualified module, so ``python
quantum_reasoning_skill/benchmark/validate_submission.py`` keeps working.
"""

from __future__ import annotations

from pathlib import Path

__all__ = ["REPO_ROOT", "package_root"]

#: Source-checkout root, i.e. the directory that contains the ``quantum_reasoning_skill``
#: package. When the distribution is installed this is the ``site-packages`` parent,
#: which is harmless: nothing in the package reads it at import time.
REPO_ROOT = Path(__file__).resolve().parents[2]

#: Modules that must live beside this file for the package to be intact.
_EXPECTED_MODULES = ("evaluate.py", "validate_submission.py", "paths.py")


def _verify_integrity() -> None:
    """Fail loudly if this package's modules appear to have been substituted.

    This is an integrity marker, not a security boundary. Python puts the
    current working directory at the front of ``sys.path`` before any of this
    repository's code runs, so a directory that shadows the whole
    ``quantum_reasoning_skill`` package wins before this package is ever
    imported, and no code inside the package can undo that. What this check does
    buy is that the common substitution -- a bare ``benchmark/__init__.py``
    planted in a working directory -- now raises instead of quietly serving code
    the caller believes is the repository's own.

    The guarantee this module does provide is in the import statements
    themselves: nothing is ever imported as a top-level module name, so an
    ``evaluate.py`` in the working directory or on ``PYTHONPATH`` can never
    shadow :mod:`quantum_reasoning_skill.benchmark.evaluate`.
    """
    here = Path(__file__).resolve().parent
    missing = [name for name in _EXPECTED_MODULES if not (here / name).is_file()]
    if missing:
        raise ImportError(
            f"benchmark package at {here} is incomplete; missing {missing}. "
            "Refusing to run against a possibly substituted benchmark package."
        )


_verify_integrity()


def package_root() -> Path:
    """Return the directory that holds this package's modules."""
    return Path(__file__).resolve().parent
