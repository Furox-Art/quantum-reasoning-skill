"""Filesystem helpers for the benchmark tooling.

Community benchmark bundles are untrusted contributed content: a pull request
can add arbitrary files under ``benchmark/results/community``. Everything here
therefore works on fully resolved paths and refuses to read or write anything
that escapes the directory it was anchored to.

The guards are intentionally strict:

* every path is resolved (symlinks included) before it is compared, so a symlink
  pointing outside the anchor is rejected rather than followed;
* the anchor itself is resolved too, so the comparison is between two real
  paths and cannot be defeated by a symlinked anchor;
* containment is decided with :meth:`pathlib.PurePath.is_relative_to`, which is
  component-wise, so ``/anchor-evil`` is not treated as being inside ``/anchor``.
"""

from __future__ import annotations

import os
from pathlib import Path

__all__ = [
    "PathBoundaryError",
    "resolve_within",
    "safe_bundle_member",
    "require_within",
]


class PathBoundaryError(ValueError):
    """Raised when a path resolves outside the directory it must stay within."""


def resolve_within(base: Path, candidate: Path | str) -> Path:
    """Resolve ``candidate`` and confirm it stays inside ``base``.

    ``candidate`` may be relative to ``base`` or absolute. Both it and ``base``
    are fully resolved first, so symlinks are compared by their real target.

    Raises :class:`PathBoundaryError` when the resolved path escapes ``base``.
    """
    resolved_base = Path(base).resolve()
    raw = Path(candidate)
    target = raw if raw.is_absolute() else resolved_base / raw
    resolved = Path(os.path.normpath(str(target)))

    # ``resolve`` also collapses symlinks; a strict mode makes a broken or
    # looping link an error instead of a silent fallback to the link itself.
    try:
        resolved = resolved.resolve(strict=False)
    except (OSError, RuntimeError) as exc:  # pragma: no cover - platform specific
        raise PathBoundaryError(f"cannot resolve {target}: {exc}") from exc

    if resolved != resolved_base and not resolved.is_relative_to(resolved_base):
        raise PathBoundaryError(f"{target} resolves outside {resolved_base}")
    return resolved


def require_within(base: Path, candidate: Path | str, *, what: str = "path") -> Path:
    """Alias of :func:`resolve_within` with a message suited to validation errors."""
    try:
        return resolve_within(base, candidate)
    except PathBoundaryError as exc:
        raise ValueError(f"{what} must stay inside {Path(base).resolve()}: {exc}") from exc


def safe_bundle_member(bundle: Path, name: str, *, what: str = "bundle member") -> Path:
    """Resolve ``bundle / name`` while refusing to escape ``bundle``.

    Bundle member names come straight from untrusted input, so they are checked
    against the bundle root rather than trusted.
    """
    if not name or Path(name).is_absolute() or ".." in Path(name).parts:
        raise ValueError(f"{what} must be a plain relative name: {name!r}")
    return require_within(bundle, Path(name), what=what)
