#!/usr/bin/env python3
"""Wait for required GitHub check runs to reach a terminal state.

Used by the release workflow before tagging. The workflow is triggered by a
push to the default branch, which starts the validation workflow *at the same
moment*. Querying the check runs once therefore races the validation run: the
checks do not exist yet, and treating that as "not passed" makes every release
fail on a green commit.

This polls with a bounded deadline instead. A check that is missing, queued or
in progress keeps the loop going. Only a genuinely terminal non-success
conclusion, or the deadline expiring, refuses.

The decision logic is a pure function over check-run records so it can be unit
tested without touching the network or the clock.

Exit codes:
    0  every required check succeeded
    1  a required check failed, was cancelled, or never appeared
    2  the check-run state could not be read at all
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from collections.abc import Callable, Iterable, Sequence
from typing import Any

#: Check-run statuses that mean the run has not finished yet.
PENDING_STATUSES = frozenset({"queued", "in_progress", "waiting", "requested", "pending"})

#: Check-run conclusions that are a real refusal. `neutral` and `skipped` are
#: treated as success because GitHub uses them for non-blocking workflows, but a
#: conclusion of `success` is the only other state we accept.
FAILING_CONCLUSIONS = frozenset({"failure", "cancelled", "timed_out", "action_required", "stale"})

CheckRuns = Sequence[dict[str, Any]]
Fetch = Callable[[], CheckRuns]


def select_checks(
    check_runs: Iterable[dict[str, Any]], contexts: Iterable[str]
) -> dict[str, list[dict[str, Any]]]:
    """Group check runs by name, keeping only the requested contexts.

    A context can legitimately have more than one check run (for example a
    re-run). Every one of them must succeed.
    """
    wanted = set(contexts)
    grouped: dict[str, list[dict[str, Any]]] = {name: [] for name in wanted}
    for run in check_runs:
        name = str(run.get("name", ""))
        if name in wanted:
            grouped[name].append(run)
    return grouped


def evaluate(  # noqa: C901 - a flat decision table reads better than nesting
    grouped: dict[str, list[dict[str, Any]]],
) -> tuple[str, list[str]]:
    """Decide whether the required checks are done.

    Returns ``(state, reasons)`` where state is one of:

    ``ready``
        every required context is present and concluded ``success``.
    ``pending``
        at least one context is missing, queued or in progress. Never a refusal.
    ``failed``
        a context concluded with a failing conclusion, or had no run at all once
        the caller stopped waiting.
    """
    reasons: list[str] = []
    failed = False
    pending = False

    for context, runs in sorted(grouped.items()):
        if not runs:
            reasons.append(f"{context}: no check run reported yet")
            pending = True
            continue
        for run in runs:
            status = str(run.get("status") or "")
            conclusion = run.get("conclusion")
            label = f"{context} ({status}/{conclusion})"
            if status and status in PENDING_STATUSES:
                reasons.append(f"{label}: still running")
                pending = True
            elif conclusion is None:
                # No conclusion and not a known pending status: the run exists
                # but has not reported. Treat as in-flight, never as a refusal.
                reasons.append(f"{label}: no conclusion reported yet")
                pending = True
            elif conclusion in FAILING_CONCLUSIONS:
                reasons.append(f"{label}: {conclusion}")
                failed = True
            elif conclusion in {"success", "skipped", "neutral"}:
                reasons.append(f"{label}: {conclusion}")
            else:
                reasons.append(f"{label}: unrecognised conclusion {conclusion!r}")
                failed = True

    if failed:
        return "failed", reasons
    if pending:
        return "pending", reasons
    return "ready", reasons


def wait_for_checks(
    fetch: Fetch,
    contexts: Sequence[str],
    *,
    timeout_seconds: float = 300.0,
    interval_seconds: float = 15.0,
    sleep: Callable[[float], None] = time.sleep,
    monotonic: Callable[[], float] = time.monotonic,
    now: Callable[[], float] = time.time,
) -> tuple[str, list[str], list[dict[str, Any]]]:
    """Poll ``fetch`` until every required check is done or time runs out.

    ``sleep`` and ``monotonic`` are injectable so tests can drive the loop
    without real time passing.

    Returns ``(state, reasons, check_runs)``.
    """
    deadline = monotonic() + timeout_seconds
    attempts = 0
    while True:
        attempts += 1
        check_runs = fetch()
        grouped = select_checks(check_runs, contexts)
        state, reasons = evaluate(grouped)
        if state == "ready":
            return "ready", reasons, list(check_runs)
        if state == "failed":
            return "failed", reasons, list(check_runs)
        if monotonic() >= deadline:
            reasons.append(
                f"gave up after {timeout_seconds:.0f}s and {attempts} attempt(s) "
                "waiting for required checks"
            )
            return "failed", reasons, list(check_runs)
        sleep(interval_seconds)


def fetch_check_runs(repo: str, ref: str, *, gh_binary: str = "gh") -> Fetch:
    """Return a callable that queries the check runs for ``ref`` via the gh CLI."""

    def _fetch() -> CheckRuns:
        completed = subprocess.run(  # noqa: S603 - fixed argv, no shell
            [
                gh_binary,
                "api",
                f"repos/{repo}/commits/{ref}/check-runs",
                "--paginate",
                "--jq",
                ".check_runs[] | {name: .name, status: .status, conclusion: .conclusion}",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode != 0:
            raise RuntimeError(
                f"could not read check runs for {ref}: "
                f"{completed.stderr.strip() or completed.stdout.strip()}"
            )
        payload = completed.stdout.strip()
        if not payload:
            return []
        runs = []
        for line in payload.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                runs.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise RuntimeError(f"could not parse check-run payload: {exc}") from exc
        return runs

    return _fetch


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="wait-for-required-checks",
        description="Poll GitHub check runs until the required contexts are terminal.",
    )
    parser.add_argument("--repo", required=True, help="owner/name")
    parser.add_argument("--ref", required=True, help="commit SHA to inspect")
    parser.add_argument(
        "--context",
        action="append",
        dest="contexts",
        required=True,
        help="required check context; repeat for more than one",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=300.0,
        help="seconds to wait before giving up (default: 300)",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=15.0,
        help="seconds between polls (default: 15)",
    )
    args = parser.parse_args(argv)

    fetch = fetch_check_runs(args.repo, args.ref)
    try:
        state, reasons, _ = wait_for_checks(
            fetch,
            args.contexts,
            timeout_seconds=args.timeout,
            interval_seconds=args.interval,
        )
    except RuntimeError as exc:
        print(f"::error::{exc}", file=sys.stderr)
        return 2

    for reason in reasons:
        print(f"  {reason}")

    if state == "ready":
        print(f"All required checks passed for {args.ref[:7]}: {', '.join(args.contexts)}")
        return 0

    if any("still running" in reason or "yet" in reason for reason in reasons):
        print(
            f"::error::Required checks did not reach a successful terminal state for "
            f"{args.ref[:7]} within {args.timeout:.0f}s. Refusing to tag. "
            f"Last observed: {'; '.join(reasons)}",
            file=sys.stderr,
        )
    else:
        print(
            f"::error::A required check failed for {args.ref[:7]}. Refusing to tag. "
            f"{'; '.join(reasons)}",
            file=sys.stderr,
        )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
