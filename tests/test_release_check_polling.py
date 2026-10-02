"""Tests for the release workflow's required-check polling loop.

``publish-release`` is triggered by the same push that starts ``validate-skill``,
so its ``verify`` job used to query the check runs once, see ``pending`` while the
validation run was still starting, and refuse to tag a green commit.

These tests pin the intended behaviour:

* a pending-then-success sequence is tolerated and resolves to ``ready``;
* a genuine failure, cancellation or timeout refuses immediately;
* a check that never appears refuses only once the deadline expires;
* a failed context is never masked by another context still running.

No network access and no real sleeping: the loop takes injectable ``sleep``,
``monotonic`` and ``fetch`` callables.
"""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load_module():
    path = ROOT / "bin" / "wait_for_required_checks.py"
    spec = importlib.util.spec_from_file_location("wait_for_required_checks", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


waiter = _load_module()

REQUIRED = ["installed API contract"]


def run(name: str, status: str, conclusion: str | None = None) -> dict:
    """Build one check-run record."""
    return {"name": name, "status": status, "conclusion": conclusion}


class FakeClock:
    """A monotonic clock and sleep function that advance without real time."""

    def __init__(self) -> None:
        self.now = 0.0
        self.slept: list[float] = []

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.now += seconds

    def time(self) -> float:
        return self.now


def sequenced(*responses: list[dict]) -> tuple[callable, list[int]]:
    """Return a fetch callable replaying ``responses``, then repeating the last."""
    calls = {"n": 0}

    def fetch() -> list[dict]:
        index = min(calls["n"], len(responses) - 1)
        calls["n"] += 1
        return list(responses[index])

    return fetch, calls


class EvaluateTests(unittest.TestCase):
    """The pure decision table over grouped check runs."""

    def test_missing_context_is_pending_not_failed(self):
        grouped = waiter.select_checks([], REQUIRED)
        state, reasons = waiter.evaluate(grouped)
        self.assertEqual(state, "pending")
        self.assertIn("no check run reported yet", reasons[0])

    def test_queued_is_pending(self):
        grouped = waiter.select_checks([run("installed API contract", "queued", None)], REQUIRED)
        state, _ = waiter.evaluate(grouped)
        self.assertEqual(state, "pending")

    def test_in_progress_is_pending(self):
        grouped = waiter.select_checks(
            [run("installed API contract", "in_progress", None)], REQUIRED
        )
        state, _ = waiter.evaluate(grouped)
        self.assertEqual(state, "pending")

    def test_run_with_no_conclusion_is_pending(self):
        grouped = waiter.select_checks([run("installed API contract", "completed", None)], REQUIRED)
        state, reasons = waiter.evaluate(grouped)
        self.assertEqual(state, "pending")
        self.assertIn("no conclusion reported yet", reasons[0])

    def test_success_is_ready(self):
        grouped = waiter.select_checks(
            [run("installed API contract", "completed", "success")], REQUIRED
        )
        state, _ = waiter.evaluate(grouped)
        self.assertEqual(state, "ready")

    def test_failure_fails(self):
        grouped = waiter.select_checks(
            [run("installed API contract", "completed", "failure")], REQUIRED
        )
        state, _ = waiter.evaluate(grouped)
        self.assertEqual(state, "failed")

    def test_cancelled_fails(self):
        grouped = waiter.select_checks(
            [run("installed API contract", "completed", "cancelled")], REQUIRED
        )
        state, _ = waiter.evaluate(grouped)
        self.assertEqual(state, "failed")

    def test_timed_out_fails(self):
        grouped = waiter.select_checks(
            [run("installed API contract", "completed", "timed_out")], REQUIRED
        )
        state, _ = waiter.evaluate(grouped)
        self.assertEqual(state, "failed")

    def test_unknown_conclusion_fails_closed(self):
        grouped = waiter.select_checks(
            [run("installed API contract", "completed", "something_new")], REQUIRED
        )
        state, _ = waiter.evaluate(grouped)
        self.assertEqual(state, "failed")

    def test_a_failure_outranks_a_pending_sibling(self):
        """A real failure must not be masked by another context still running."""
        contexts = ["installed API contract", "lint"]
        runs = [
            run("installed API contract", "completed", "failure"),
            run("lint", "in_progress", None),
        ]
        state, _ = waiter.evaluate(waiter.select_checks(runs, contexts))
        self.assertEqual(state, "failed")

    def test_every_rerun_of_a_context_must_succeed(self):
        runs = [
            run("installed API contract", "completed", "success"),
            run("installed API contract", "completed", "failure"),
        ]
        state, _ = waiter.evaluate(waiter.select_checks(runs, REQUIRED))
        self.assertEqual(state, "failed")


class WaitLoopTests(unittest.TestCase):
    """The bounded polling loop."""

    def test_pending_then_success_is_tolerated(self):
        """The regression this loop exists for: absent -> running -> success."""
        fetch, calls = sequenced(
            [],
            [run("installed API contract", "queued", None)],
            [run("installed API contract", "in_progress", None)],
            [run("installed API contract", "completed", "success")],
        )
        clock = FakeClock()
        state, reasons, _ = waiter.wait_for_checks(
            fetch,
            REQUIRED,
            timeout_seconds=300.0,
            interval_seconds=15.0,
            sleep=clock.sleep,
            monotonic=clock.monotonic,
        )
        self.assertEqual(state, "ready", reasons)
        self.assertEqual(calls["n"], 4)
        self.assertEqual(clock.slept, [15.0, 15.0, 15.0])

    def test_real_failure_stops_immediately(self):
        fetch, calls = sequenced([run("installed API contract", "completed", "failure")])
        clock = FakeClock()
        state, reasons, _ = waiter.wait_for_checks(
            fetch,
            REQUIRED,
            timeout_seconds=300.0,
            interval_seconds=15.0,
            sleep=clock.sleep,
            monotonic=clock.monotonic,
        )
        self.assertEqual(state, "failed")
        self.assertEqual(calls["n"], 1, "a real failure must not be retried")
        self.assertEqual(clock.slept, [])

    def test_never_appearing_fails_only_at_the_deadline(self):
        fetch, calls = sequenced([])
        clock = FakeClock()
        state, reasons, _ = waiter.wait_for_checks(
            fetch,
            REQUIRED,
            timeout_seconds=60.0,
            interval_seconds=15.0,
            sleep=clock.sleep,
            monotonic=clock.monotonic,
        )
        self.assertEqual(state, "failed")
        self.assertTrue(any("gave up after" in reason for reason in reasons))
        # 60s / 15s = four polls, then the deadline check trips.
        self.assertEqual(calls["n"], 5)
        self.assertEqual(sum(clock.slept), 60.0)

    def test_in_progress_until_deadline_fails_at_deadline(self):
        fetch, _ = sequenced([run("installed API contract", "in_progress", None)])
        clock = FakeClock()
        state, reasons, _ = waiter.wait_for_checks(
            fetch,
            REQUIRED,
            timeout_seconds=30.0,
            interval_seconds=10.0,
            sleep=clock.sleep,
            monotonic=clock.monotonic,
        )
        self.assertEqual(state, "failed")
        self.assertTrue(any("gave up after" in reason for reason in reasons))

    def test_failure_after_several_polls_refuses(self):
        fetch, calls = sequenced(
            [],
            [run("installed API contract", "in_progress", None)],
            [run("installed API contract", "completed", "cancelled")],
        )
        clock = FakeClock()
        state, reasons, _ = waiter.wait_for_checks(
            fetch,
            REQUIRED,
            timeout_seconds=300.0,
            interval_seconds=15.0,
            sleep=clock.sleep,
            monotonic=clock.monotonic,
        )
        self.assertEqual(state, "failed")
        self.assertEqual(calls["n"], 3)
        self.assertTrue(any("cancelled" in reason for reason in reasons))

    def test_all_required_contexts_must_pass(self):
        contexts = ["installed API contract", "repository contract"]
        fetch, _ = sequenced(
            [
                run("installed API contract", "completed", "success"),
                run("repository contract", "in_progress", None),
            ]
        )
        clock = FakeClock()
        state, _, _ = waiter.wait_for_checks(
            fetch,
            contexts,
            timeout_seconds=45.0,
            interval_seconds=15.0,
            sleep=clock.sleep,
            monotonic=clock.monotonic,
        )
        self.assertEqual(state, "failed")


class WorkflowShapeTests(unittest.TestCase):
    """The workflow must use the loop rather than a single query."""

    def setUp(self) -> None:
        self.text = (ROOT / ".github" / "workflows" / "publish-release.yml").read_text(
            encoding="utf-8"
        )

    def test_verify_waits_instead_of_querying_once(self):
        self.assertIn("wait_for_required_checks.py", self.text)

    def test_no_single_shot_check_runs_query_remains(self):
        self.assertNotIn('check-runs" --paginate', self.text)
        self.assertNotIn('else "pending"', self.text)

    def test_timeout_is_bounded(self):
        self.assertIn("--timeout 300", self.text)

    def test_privileged_job_still_gated_on_the_wait(self):
        self.assertIn("needs.verify.outputs.ready == 'yes'", self.text)

    def test_workflow_is_still_gated_on_the_default_branch(self):
        self.assertIn("github.ref == 'refs/heads/main'", self.text)


if __name__ == "__main__":
    unittest.main()
