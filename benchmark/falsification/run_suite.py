"""Controlled single-hypothesis vs multi-hypothesis falsification benchmark.

The runner drives two reasoning policies over identical deterministic scenario
streams and reports per-scenario and aggregate metrics. It uses only the Python
standard library and makes no network or LLM API calls.

Policies
--------
``single``
    Commits to the strongest branch at each step and never reconsiders it. This
    is the "first plausible answer wins" behaviour the skill argues against.

``multi``
    Runs the reference branch controller from
    ``reference/branch_controller.py``: branches are scored from explicit
    metric snapshots, contradicted branches are pruned, dormant branches are
    revived on material evidence change, and the final answer is the surviving
    leader. Rejected branches are reopened only when their rejection premise is
    explicitly invalidated by the scenario.

Metrics (all computed by this file, all deterministic)
-----------------------------------------------------
- final accuracy: fraction of scenarios whose final answer matches ground truth
- decision-switch success: fraction of falsification scenarios where the wrong
  leader was abandoned within ``switch_window`` evidence steps after it became
  falsified, plus the mean number of evidence steps taken to abandon it
- calibration: multiclass Brier score of the reported probability vector over
  the surviving branches at each step where an answer is committed
- latency: measured wall-clock milliseconds per decision
- cost: deterministic token estimate per evidence step per surviving branch
- revival success: fraction of revival scenarios where the required branch was
  correctly re-evaluated after being dormant or rejected
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from benchmark.falsification.scenarios import (  # noqa: E402
    Scenario,
    build_all_scenarios,
    scenario_as_case_record,
)
from reference import branch_controller as BC  # noqa: E402

# Deterministic token accounting. Tokens are a fixed per-branch per-step budget
# plus a fixed per-decision overhead, so cost differences come only from how
# many branches each policy keeps alive.
TOKENS_PER_BRANCH_STEP = 12
TOKENS_PER_DECISION = 8
TOKENS_PER_VERIFICATION_STEP = 6

SWITCH_WINDOW = 1


@dataclass
class StepRecord:
    step: int
    leader: str
    leader_score: float
    probabilities: dict[str, float]
    answer_committed: bool
    correct: bool | None
    active_branches: int
    dormant_branches: int
    rejected_branches: int
    revived_this_step: list[str] = field(default_factory=list)
    falsified_this_step: list[str] = field(default_factory=list)
    collapsed: bool = False
    collapse_reason: str = ""
    tokens: int = 0
    latency_ms: float = 0.0


@dataclass
class ScenarioResult:
    scenario_id: str
    scenario_type: str
    policy: str
    final_answer: str
    truth: str
    correct: bool
    steps: list[StepRecord]
    total_tokens: int
    total_latency_ms: float
    mean_latency_ms: float
    # falsification-specific
    switch_success: bool | None
    switch_delay_steps: int | None
    wrong_leader_steps: int
    # revival-specific
    revival_success: bool | None
    # calibration
    brier: float | None
    probability_rows: list[dict[str, Any]] = field(default_factory=list)


def _softmax_scores(scores: dict[str, float], temperature: float = 0.15) -> dict[str, float]:
    """Convert branch support scores into a reported probability vector.

    Deterministic. Probabilities are computed over the branch's current support
    score so that a run's stated confidence tracks its evidence, which is what
    makes Brier-score calibration meaningful for this benchmark.
    """
    ids = sorted(scores)
    if not ids:
        return {}
    scaled = {branch: scores[branch] / temperature for branch in ids}
    top = max(scaled.values())
    exps = {branch: pow(2.718281828459045, scaled[branch] - top) for branch in ids}
    total = sum(exps.values())
    if total <= 0:
        uniform = 1.0 / len(ids)
        return dict.fromkeys(ids, uniform)
    return {branch: exps[branch] / total for branch in ids}


def _metrics_from_snapshot(snapshot: dict[str, dict[str, float]]) -> dict[str, Any]:
    return {branch_id: BC.BranchMetrics(**values) for branch_id, values in snapshot.items()}


def _run_multi_policy(scenario: Scenario) -> ScenarioResult:
    """Drive the reference branch controller over the scenario evidence stream."""
    branches: dict[str, Any] = {}
    step_records: list[StepRecord] = []
    probability_rows: list[dict[str, Any]] = []
    revived_target_seen = False
    falsified_step: int | None = None
    abandoned_step: int | None = None
    wrong_leader_steps = 0
    total_tokens = 0
    total_latency_ms = 0.0

    previous_metrics: dict[str, Any] = {}
    reopen_candidates: set[str] = set()

    for step in scenario.steps:
        step_start = time.perf_counter()
        metrics = _metrics_from_snapshot(step.metrics)

        # Track falsification of the decoy branch: the step at which its
        # contradiction first reaches the rejection threshold.
        if scenario.decoy_branch is not None and falsified_step is None:
            decoy_metrics = metrics.get(scenario.decoy_branch)
            if decoy_metrics is not None and (
                decoy_metrics.contradiction >= BC.DEFAULT_THRESHOLDS.reject_contradiction
            ):
                falsified_step = step.step

        for branch_id, current in metrics.items():
            if branch_id in branches:
                existing = branches[branch_id]
                branches[branch_id] = BC.Branch(
                    branch_id=branch_id,
                    metrics=current,
                    state=existing.state,
                    previous_metrics=previous_metrics.get(branch_id),
                )
            else:
                branches[branch_id] = BC.Branch(
                    branch_id=branch_id,
                    metrics=current,
                    state=BC.BranchState.ACTIVE,
                    previous_metrics=None,
                )

            # Explicit reopen: the scenario invalidates the premise that caused
            # a rejection, so the runner reopens the branch for re-evaluation.
            if (
                branch_id in reopen_candidates
                and branches[branch_id].state == BC.BranchState.REJECTED
            ):
                branches[branch_id] = BC.Branch(
                    branch_id=branch_id,
                    metrics=current,
                    state=BC.BranchState.DORMANT,
                    previous_metrics=previous_metrics.get(branch_id),
                )

        # Apply controller transitions.
        revived_this_step: list[str] = []
        falsified_this_step: list[str] = []
        for branch_id in list(branches):
            before = branches[branch_id]
            after = BC.update_branch_state(before)
            branches[branch_id] = after
            if (
                before.state == BC.BranchState.REJECTED
                and after.state != BC.BranchState.REJECTED
                or before.state in (BC.BranchState.DORMANT, BC.BranchState.REJECTED)
                and (after.state == BC.BranchState.ACTIVE)
            ):
                revived_this_step.append(branch_id)
            if after.state == BC.BranchState.REJECTED and before.state != BC.BranchState.REJECTED:
                falsified_this_step.append(branch_id)

        # Revival bookkeeping for the scenario's designated revival branch.
        if (
            scenario.revived_branch is not None
            and scenario.revival_step is not None
            and step.step >= scenario.revival_step
        ):
            target = branches.get(scenario.revived_branch)
            if target is not None and target.state != BC.BranchState.REJECTED:
                revived_target_seen = True
        if scenario.revived_branch in falsified_this_step:
            reopen_candidates.add(scenario.revived_branch)

        ranked = BC.rank_branches(list(branches.values()))
        scores = {branch.branch_id: BC.branch_score(branch.metrics) for branch in ranked}
        probabilities = _softmax_scores(scores)
        leader_id = ranked[0].branch_id if ranked else ""
        leader_score = scores.get(leader_id, 0.0)

        if leader_id == scenario.truth_branch:
            abandoned_step = abandoned_step or step.step

        if scenario.decoy_branch is not None and leader_id == scenario.decoy_branch:
            wrong_leader_steps += 1

        active = sum(1 for b in branches.values() if b.state == BC.BranchState.ACTIVE)
        dormant = sum(1 for b in branches.values() if b.state == BC.BranchState.DORMANT)
        rejected = sum(1 for b in branches.values() if b.state == BC.BranchState.REJECTED)

        can_collapse, collapse_reason, _ = BC.collapse_decision(list(branches.values()))
        if can_collapse:
            collapse_reason = "collapse criteria satisfied"

        tokens = (
            TOKENS_PER_DECISION
            + TOKENS_PER_BRANCH_STEP * (active + dormant)
            + TOKENS_PER_VERIFICATION_STEP * active
        )
        step_latency = (time.perf_counter() - step_start) * 1000.0
        total_tokens += tokens
        total_latency_ms += step_latency

        correct_answer: bool | None = None
        if step.answer_known_from and leader_id:
            correct_answer = leader_id == scenario.truth_branch

        step_records.append(
            StepRecord(
                step=step.step,
                leader=leader_id,
                leader_score=round(leader_score, 6),
                probabilities={branch: round(value, 6) for branch, value in probabilities.items()},
                answer_committed=bool(step.answer_known_from),
                correct=correct_answer,
                active_branches=active,
                dormant_branches=dormant,
                rejected_branches=rejected,
                revived_this_step=revived_this_step,
                falsified_this_step=falsified_this_step,
                collapsed=can_collapse,
                collapse_reason=collapse_reason,
                tokens=tokens,
                latency_ms=round(step_latency, 6),
            )
        )
        if step.answer_known_from:
            probability_rows.append(
                {
                    "step": step.step,
                    "scenario_id": scenario.id,
                    "truth": scenario.truth_branch,
                    "probabilities": probabilities,
                }
            )

        previous_metrics = {branch_id: branch.metrics for branch_id, branch in branches.items()}

    final_answer = step_records[-1].leader if step_records else ""
    switch_success: bool | None = None
    switch_delay: int | None = None
    if scenario.decoy_branch is not None and falsified_step is not None:
        if abandoned_step is not None and abandoned_step <= falsified_step + SWITCH_WINDOW:
            switch_success = True
            switch_delay = abandoned_step - falsified_step
        else:
            switch_success = False
            switch_delay = None if abandoned_step is None else abandoned_step - falsified_step

    revival_success: bool | None = None
    if scenario.revived_branch is not None:
        revival_success = bool(revived_target_seen)

    brier = _brier_from_rows(probability_rows) if probability_rows else None

    return ScenarioResult(
        scenario_id=scenario.id,
        scenario_type=scenario.scenario_type,
        policy="multi",
        final_answer=final_answer,
        truth=scenario.truth_branch,
        correct=final_answer == scenario.truth_branch,
        steps=step_records,
        total_tokens=total_tokens,
        total_latency_ms=total_latency_ms,
        mean_latency_ms=total_latency_ms / len(step_records) if step_records else 0.0,
        switch_success=switch_success,
        switch_delay_steps=switch_delay,
        wrong_leader_steps=wrong_leader_steps,
        revival_success=revival_success,
        brier=brier,
        probability_rows=probability_rows,
    )


def _brier_from_rows(rows: Iterable[dict[str, Any]]) -> float:
    """Multiclass Brier score over all reported probability rows.

    For each row the score is sum over branches of (p_reported - outcome)^2,
    where outcome is 1 for the truth branch and 0 otherwise. Lower is better;
    0 is perfect and confident-wrong answers score close to 2.
    """
    total = 0.0
    count = 0
    for row in rows:
        truth = row["truth"]
        for branch, probability in row["probabilities"].items():
            outcome = 1.0 if branch == truth else 0.0
            total += (probability - outcome) ** 2
            count += 1
    if count == 0:
        return 0.0
    return total / count


def _run_single_policy(scenario: Scenario) -> ScenarioResult:
    """Commit to the strongest branch at step 1 and never revisit it."""
    step_records: list[StepRecord] = []
    probability_rows: list[dict[str, Any]] = []
    total_tokens = 0
    total_latency_ms = 0.0

    # Single-hypothesis policy: the first strongest branch is locked in.
    first_scores = {
        branch_id: BC.branch_score(BC.BranchMetrics(**values))
        for branch_id, values in scenario.steps[0].metrics.items()
    }
    committed = max(sorted(first_scores), key=lambda b: first_scores[b])

    for step in scenario.steps:
        step_start = time.perf_counter()
        metrics = _metrics_from_snapshot(step.metrics)
        scores = {
            branch_id: BC.branch_score(bc_metrics) for branch_id, bc_metrics in metrics.items()
        }
        probabilities = _softmax_scores(scores)
        leader_id = committed
        leader_score = scores.get(leader_id, 0.0)

        active = 1
        dormant = 0
        rejected = 0
        tokens = (
            TOKENS_PER_DECISION
            + TOKENS_PER_BRANCH_STEP * active
            + TOKENS_PER_VERIFICATION_STEP * active
        )
        step_latency = (time.perf_counter() - step_start) * 1000.0
        total_tokens += tokens
        total_latency_ms += step_latency

        correct_answer: bool | None = None
        if step.answer_known_from:
            correct_answer = leader_id == scenario.truth_branch

        step_records.append(
            StepRecord(
                step=step.step,
                leader=leader_id,
                leader_score=round(leader_score, 6),
                probabilities={branch: round(value, 6) for branch, value in probabilities.items()},
                answer_committed=bool(step.answer_known_from),
                correct=correct_answer,
                active_branches=active,
                dormant_branches=dormant,
                rejected_branches=rejected,
                revived_this_step=[],
                falsified_this_step=[],
                collapsed=False,
                collapse_reason="single-hypothesis policy never reconsiders",
                tokens=tokens,
                latency_ms=round(step_latency, 6),
            )
        )
        if step.answer_known_from:
            probability_rows.append(
                {
                    "step": step.step,
                    "scenario_id": scenario.id,
                    "truth": scenario.truth_branch,
                    "probabilities": probabilities,
                }
            )

    switch_success: bool | None = None
    switch_delay: int | None = None
    if scenario.decoy_branch is not None:
        if committed != scenario.decoy_branch:
            switch_success = True
            switch_delay = 0
        else:
            switch_success = False
            switch_delay = None

    revival_success: bool | None = None
    if scenario.revived_branch is not None:
        revival_success = committed == scenario.revived_branch

    brier = _brier_from_rows(probability_rows) if probability_rows else None

    return ScenarioResult(
        scenario_id=scenario.id,
        scenario_type=scenario.scenario_type,
        policy="single",
        final_answer=committed,
        truth=scenario.truth_branch,
        correct=committed == scenario.truth_branch,
        steps=step_records,
        total_tokens=total_tokens,
        total_latency_ms=total_latency_ms,
        mean_latency_ms=total_latency_ms / len(step_records) if step_records else 0.0,
        switch_success=switch_success,
        switch_delay_steps=switch_delay,
        wrong_leader_steps=0,
        revival_success=revival_success,
        brier=brier,
        probability_rows=probability_rows,
    )


def run_suite(
    scenarios: list[Scenario],
    policies: Iterable[str] = ("single", "multi"),
) -> list[ScenarioResult]:
    results: list[ScenarioResult] = []
    for scenario in scenarios:
        for policy in policies:
            if policy == "single":
                results.append(_run_single_policy(scenario))
            elif policy == "multi":
                results.append(_run_multi_policy(scenario))
            else:
                raise ValueError(f"unknown policy: {policy}")
    return results


def _mean(values: Iterable[float | None]) -> float | None:
    materialized = [value for value in values if value is not None]
    if not materialized:
        return None
    return sum(materialized) / len(materialized)


def aggregate(results: list[ScenarioResult]) -> dict[str, Any]:
    """Aggregate per-scenario results into the published summary metrics."""
    by_policy: dict[str, list[ScenarioResult]] = {}
    for result in results:
        by_policy.setdefault(result.policy, []).append(result)

    def policy_block(policy: str) -> dict[str, Any]:
        rows = by_policy[policy]
        falsification = [r for r in rows if r.scenario_type == "falsification"]
        revival = [r for r in rows if r.scenario_type == "revival"]
        control = [r for r in rows if r.scenario_type == "control"]

        accuracy = sum(1 for r in rows if r.correct) / len(rows) if rows else None
        switch_rows = [r for r in falsification if r.switch_success is not None]
        switch_success = (
            sum(1 for r in switch_rows if r.switch_success) / len(switch_rows)
            if switch_rows
            else None
        )
        switch_delays = [
            r.switch_delay_steps for r in switch_rows if r.switch_delay_steps is not None
        ]
        revival_rows = [r for r in revival if r.revival_success is not None]
        revival_success = (
            sum(1 for r in revival_rows if r.revival_success) / len(revival_rows)
            if revival_rows
            else None
        )
        brier_rows = [r for r in rows if r.brier is not None]
        return {
            "scenarios": len(rows),
            "accuracy": accuracy,
            "falsification": {
                "scenarios": len(falsification),
                "accuracy": (
                    sum(1 for r in falsification if r.correct) / len(falsification)
                    if falsification
                    else None
                ),
                "decision_switch_success_rate": switch_success,
                "mean_switch_delay_steps": _mean(switch_delays),
                "switch_events": len(switch_rows),
            },
            "revival": {
                "scenarios": len(revival),
                "revival_success_rate": revival_success,
                "accuracy": (
                    sum(1 for r in revival if r.correct) / len(revival) if revival else None
                ),
            },
            "control": {
                "scenarios": len(control),
                "accuracy": (
                    sum(1 for r in control if r.correct) / len(control) if control else None
                ),
            },
            "brier_score": _mean(r.brier for r in brier_rows),
            "mean_tokens_per_scenario": _mean(float(r.total_tokens) for r in rows),
            "mean_latency_ms_per_decision": _mean(r.mean_latency_ms for r in rows if r.steps),
            "total_latency_ms": sum(r.total_latency_ms for r in rows),
        }

    payload = {policy: policy_block(policy) for policy in ("single", "multi")}
    if "single" in payload and "multi" in payload:
        payload["comparison"] = {
            "accuracy_delta": (
                payload["multi"]["accuracy"] - payload["single"]["accuracy"]
                if payload["multi"]["accuracy"] is not None
                and payload["single"]["accuracy"] is not None
                else None
            ),
            "falsification_accuracy_delta": (
                payload["multi"]["falsification"]["accuracy"]
                - payload["single"]["falsification"]["accuracy"]
                if payload["multi"]["falsification"]["accuracy"] is not None
                and payload["single"]["falsification"]["accuracy"] is not None
                else None
            ),
            "decision_switch_success_delta": (
                payload["multi"]["falsification"]["decision_switch_success_rate"]
                - payload["single"]["falsification"]["decision_switch_success_rate"]
                if payload["multi"]["falsification"]["decision_switch_success_rate"] is not None
                and payload["single"]["falsification"]["decision_switch_success_rate"] is not None
                else None
            ),
            "revival_success_delta": (
                payload["multi"]["revival"]["revival_success_rate"]
                - payload["single"]["revival"]["revival_success_rate"]
                if payload["multi"]["revival"]["revival_success_rate"] is not None
                and payload["single"]["revival"]["revival_success_rate"] is not None
                else None
            ),
            "brier_delta": (
                payload["multi"]["brier_score"] - payload["single"]["brier_score"]
                if payload["multi"]["brier_score"] is not None
                and payload["single"]["brier_score"] is not None
                else None
            ),
            "token_percent_change": (
                (
                    payload["multi"]["mean_tokens_per_scenario"]
                    - payload["single"]["mean_tokens_per_scenario"]
                )
                / payload["single"]["mean_tokens_per_scenario"]
                * 100.0
                if payload["multi"]["mean_tokens_per_scenario"] is not None
                and payload["single"]["mean_tokens_per_scenario"] not in (None, 0)
                else None
            ),
        }
    return payload


def reliability_rows(results: list[ScenarioResult]) -> list[dict[str, Any]]:
    """Bucket reported probabilities for the truth branch into reliability bins."""
    rows: list[dict[str, Any]] = []
    bins = [0.0, 0.2, 0.4, 0.6, 0.8, 1.0]
    for result in results:
        for row in result.probability_rows:
            truth_probability = row["probabilities"].get(row["truth"], 0.0)
            index = 0
            for position, edge in enumerate(bins[1:], start=1):
                if truth_probability <= edge:
                    index = position - 1
                    break
            else:
                index = len(bins) - 2
            rows.append(
                {
                    "scenario_id": result.scenario_id,
                    "policy": result.policy,
                    "step": row["step"],
                    "truth_probability": truth_probability,
                    "bin": f"{bins[index]:.1f}-{bins[index + 1]:.1f}",
                }
            )
    return rows


def results_to_dicts(results: list[ScenarioResult]) -> list[dict[str, Any]]:
    payload = []
    for result in results:
        steps = []
        for step in result.steps:
            steps.append(
                {
                    "step": step.step,
                    "leader": step.leader,
                    "leader_score": step.leader_score,
                    "probabilities": step.probabilities,
                    "answer_committed": step.answer_committed,
                    "correct": step.correct,
                    "active_branches": step.active_branches,
                    "dormant_branches": step.dormant_branches,
                    "rejected_branches": step.rejected_branches,
                    "revived_this_step": step.revived_this_step,
                    "falsified_this_step": step.falsified_this_step,
                    "collapsed": step.collapsed,
                    "collapse_reason": step.collapse_reason,
                    "tokens": step.tokens,
                    "latency_ms": step.latency_ms,
                }
            )
        payload.append(
            {
                "scenario_id": result.scenario_id,
                "scenario_type": result.scenario_type,
                "policy": result.policy,
                "final_answer": result.final_answer,
                "truth": result.truth,
                "correct": result.correct,
                "total_tokens": result.total_tokens,
                "total_latency_ms": round(result.total_latency_ms, 6),
                "mean_latency_ms": round(result.mean_latency_ms, 6),
                "switch_success": result.switch_success,
                "switch_delay_steps": result.switch_delay_steps,
                "wrong_leader_steps": result.wrong_leader_steps,
                "revival_success": result.revival_success,
                "brier": round(result.brier, 6) if result.brier is not None else None,
                "steps": steps,
            }
        )
    return payload


def render_markdown_table(
    summary: dict[str, Any],
    results: list[ScenarioResult],
) -> str:
    lines: list[str] = []
    lines.append("## Aggregate summary")
    lines.append("")
    lines.append("| metric | single-hypothesis | multi-hypothesis |")
    lines.append("|---|---:|---:|")
    single = summary["single"]
    multi = summary["multi"]

    def fmt(value: Any, digits: int = 3) -> str:
        if value is None:
            return "n/a"
        if isinstance(value, float):
            return f"{value:.{digits}f}"
        return str(value)

    lines.append(f"| overall accuracy | {fmt(single['accuracy'])} | {fmt(multi['accuracy'])} |")
    lines.append(
        "| falsification-scenario accuracy | "
        f"{fmt(single['falsification']['accuracy'])} | "
        f"{fmt(multi['falsification']['accuracy'])} |"
    )
    lines.append(
        "| decision-switch success rate | "
        f"{fmt(single['falsification']['decision_switch_success_rate'])} | "
        f"{fmt(multi['falsification']['decision_switch_success_rate'])} |"
    )
    lines.append(
        "| mean switch delay (evidence steps) | "
        f"{fmt(single['falsification']['mean_switch_delay_steps'])} | "
        f"{fmt(multi['falsification']['mean_switch_delay_steps'])} |"
    )
    lines.append(
        "| revival success rate | "
        f"{fmt(single['revival']['revival_success_rate'])} | "
        f"{fmt(multi['revival']['revival_success_rate'])} |"
    )
    lines.append(
        f"| control-scenario accuracy | {fmt(single['control']['accuracy'])} | "
        f"{fmt(multi['control']['accuracy'])} |"
    )
    lines.append(
        f"| Brier score (lower is better) | {fmt(single['brier_score'])} | "
        f"{fmt(multi['brier_score'])} |"
    )
    lines.append(
        "| mean tokens per scenario | "
        f"{fmt(single['mean_tokens_per_scenario'], 1)} | "
        f"{fmt(multi['mean_tokens_per_scenario'], 1)} |"
    )
    lines.append(
        "| mean latency per decision (ms) | "
        f"{fmt(single['mean_latency_ms_per_decision'])} | "
        f"{fmt(multi['mean_latency_ms_per_decision'])} |"
    )
    lines.append("")
    lines.append("## Per-scenario results")
    lines.append("")
    lines.append(
        "| scenario | type | policy | final answer | correct | switch | revival | tokens |"
    )
    lines.append("|---|---|---|---|---|---|---|---:|")
    for result in results:
        lines.append(
            f"| {result.scenario_id} | {result.scenario_type} | {result.policy} | "
            f"{result.final_answer} | {'yes' if result.correct else 'no'} | "
            f"{_switch_text(result)} | {_revival_text(result)} | {result.total_tokens} |"
        )
    lines.append("")
    return "\n".join(lines)


def _switch_text(result: ScenarioResult) -> str:
    if result.switch_success is None:
        return "n/a"
    if result.switch_success:
        return f"yes (+{result.switch_delay_steps})"
    return "no"


def _revival_text(result: ScenarioResult) -> str:
    if result.revival_success is None:
        return "n/a"
    return "yes" if result.revival_success else "no"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("benchmark/falsification/results"),
        help="Directory for committed result artifacts (JSON + Markdown).",
    )
    parser.add_argument(
        "--cases-output",
        type=Path,
        default=Path("benchmark/falsification/scenarios.jsonl"),
        help="Path for the generated cases file.",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress the human-readable table on stdout.",
    )
    args = parser.parse_args()

    scenarios = build_all_scenarios()
    results = run_suite(scenarios)
    summary = aggregate(results)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    json_payload = {
        "suite": "falsification-comparative",
        "scenario_count": len(scenarios),
        "policies": ["single", "multi"],
        "switch_window_steps": SWITCH_WINDOW,
        "token_model": {
            "tokens_per_decision": TOKENS_PER_DECISION,
            "tokens_per_branch_step": TOKENS_PER_BRANCH_STEP,
            "tokens_per_verification_step": TOKENS_PER_VERIFICATION_STEP,
        },
        "summary": summary,
        "per_scenario": results_to_dicts(results),
        "reliability_bins": reliability_rows(results),
    }
    json_path = args.output_dir / "results.json"
    json_path.write_text(
        json.dumps(json_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    markdown_path = args.output_dir / "RESULTS.md"
    markdown_path.write_text(
        "# Falsification benchmark results\n\n" + render_markdown_table(summary, results),
        encoding="utf-8",
    )

    args.cases_output.parent.mkdir(parents=True, exist_ok=True)
    with args.cases_output.open("w", encoding="utf-8", newline="\n") as handle:
        for scenario in scenarios:
            handle.write(json.dumps(scenario_as_case_record(scenario), sort_keys=True) + "\n")

    if not args.quiet:
        print(render_markdown_table(summary, results))
        print(f"wrote {json_path}")
        print(f"wrote {markdown_path}")
        print(f"wrote {args.cases_output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
