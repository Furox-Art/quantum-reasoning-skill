"""Deterministic falsification-scenario suite for the Quantum Reasoning Skill.

This suite is provider-agnostic and uses only the Python standard library. It
drives two reasoning policies over identical, fully deterministic scenarios:

- ``single``: commit to the currently strongest hypothesis and never revisit it.
- ``multi``: the reference branch controller from ``reference/branch_controller.py``,
  which keeps alternatives alive, prunes contradicted branches, revives dormant
  branches when evidence materially improves, and collapses only when one
  verified leader clearly dominates.

The scenarios are expressed as explicit branch-metric streams with known ground
truth, so the same run always produces the same numbers. No LLM API key is
needed and no network access is performed.

Scope boundary (read this before quoting any number): these results measure the
reference *decision controller* under curated evidence streams. They are NOT a
measurement of any language model's reasoning ability. Because the metric
streams are synthetic, the results are a lower bound on real-world generality,
not evidence of model performance gains.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

SCENARIO_TYPES = ("falsification", "revival", "control")


# Evidence steps are 1-indexed. The ground-truth answer becomes known to the
# run at ``answer_known_from`` inclusive; earlier steps carry no answer credit.
@dataclass(frozen=True)
class EvidenceStep:
    step: int
    # Per-branch metric snapshots at this evidence step.
    metrics: dict[str, dict[str, float]]
    answer_known_from: bool = False
    note: str = ""


@dataclass(frozen=True)
class Scenario:
    id: str
    scenario_type: str
    domain: str
    prompt: str
    # Branch that holds the ground-truth answer.
    truth_branch: str
    # Human-readable answer, used for exact-match accuracy.
    answer: str
    accepted_answers: list[str]
    # Branch that is initially strongest but eventually falsified (falsification
    # scenarios only). ``None`` for control scenarios.
    decoy_branch: str | None
    # Evidence step at which the decoy becomes falsified. ``None`` for control.
    falsified_at_step: int | None
    # Step at which a previously dormant branch receives materially better
    # evidence and should be revived (revival scenarios only).
    revival_step: int | None
    # Branch that must be revived for the correct final answer.
    revived_branch: str | None
    steps: list[EvidenceStep] = field(default_factory=list)
    notes: str = ""


def _branch(
    evidence: float,
    verification: float,
    independence: float,
    information_gain: float,
    contradiction: float,
    unresolved_assumptions: float,
    normalized_cost: float,
    shared_assumption_ratio: float = 0.0,
    semantic_similarity_to_leader: float = 0.0,
) -> dict[str, float]:
    """Build one branch-metric snapshot with all controller inputs."""
    return {
        "evidence": evidence,
        "verification": verification,
        "independence": independence,
        "information_gain": information_gain,
        "contradiction": contradiction,
        "unresolved_assumptions": unresolved_assumptions,
        "normalized_cost": normalized_cost,
        "shared_assumption_ratio": shared_assumption_ratio,
        "semantic_similarity_to_leader": semantic_similarity_to_leader,
    }


# ---------------------------------------------------------------------------
# Scenario A - falsification: the initially strongest hypothesis is falsified
# midway and the correct alternative only becomes clearly better afterwards.
# ---------------------------------------------------------------------------
def build_falsification_scenarios() -> list[Scenario]:
    scenarios: list[Scenario] = []

    # A1: statistical sign / Simpson-style reversal. H_A (pooled trend) is
    # strongest early; the segment split at step 3 falsifies it. H_B is correct.
    a1_steps = [
        EvidenceStep(
            1,
            {
                "H_A": _branch(0.72, 0.45, 0.80, 0.55, 0.05, 0.35, 0.10),
                "H_B": _branch(0.40, 0.20, 0.85, 0.75, 0.10, 0.65, 0.05),
                "H_C": _branch(0.22, 0.15, 0.70, 0.55, 0.10, 0.80, 0.02),
            },
            note="pooled correlation favours H_A; segment confound not yet checked",
        ),
        EvidenceStep(
            2,
            {
                "H_A": _branch(0.80, 0.55, 0.80, 0.50, 0.05, 0.25, 0.18),
                "H_B": _branch(0.50, 0.30, 0.85, 0.75, 0.10, 0.55, 0.10),
                "H_C": _branch(0.28, 0.20, 0.70, 0.50, 0.10, 0.78, 0.05),
            },
            note="H_A still leading; within-segment test requested",
        ),
        EvidenceStep(
            3,
            {
                "H_A": _branch(0.35, 0.30, 0.80, 0.25, 0.90, 0.60, 0.30),
                "H_B": _branch(0.75, 0.60, 0.85, 0.65, 0.05, 0.30, 0.22),
                "H_C": _branch(0.30, 0.22, 0.70, 0.45, 0.10, 0.75, 0.08),
            },
            note="segment split reverses the effect: H_A contradicted",
        ),
        EvidenceStep(
            4,
            {
                "H_A": _branch(0.20, 0.25, 0.80, 0.10, 0.95, 0.75, 0.40),
                "H_B": _branch(0.90, 0.85, 0.85, 0.35, 0.05, 0.10, 0.35),
                "H_C": _branch(0.25, 0.20, 0.70, 0.30, 0.10, 0.85, 0.12),
            },
            answer_known_from=True,
            note="segment-level replication confirms H_B",
        ),
        EvidenceStep(
            5,
            {
                "H_A": _branch(0.18, 0.25, 0.80, 0.05, 0.95, 0.80, 0.45),
                "H_B": _branch(0.92, 0.90, 0.85, 0.20, 0.05, 0.05, 0.45),
                "H_C": _branch(0.22, 0.18, 0.70, 0.25, 0.10, 0.90, 0.16),
            },
            answer_known_from=True,
            note="H_B consolidated across both segments",
        ),
    ]
    scenarios.append(
        Scenario(
            id="falsification-001",
            scenario_type="falsification",
            domain="causal-inference",
            prompt=(
                "Pooled data shows a positive association between treatment and "
                "outcome. Within-segment analysis reverses the sign. Which "
                "hypothesis survives all evidence?"
            ),
            truth_branch="H_B",
            answer="H_B",
            accepted_answers=["H_B", "h_b", "b"],
            decoy_branch="H_A",
            falsified_at_step=3,
            revival_step=None,
            revived_branch=None,
            steps=a1_steps,
            notes="Simpson-style reversal; segment split falsifies the pooled-trend hypothesis.",
        )
    )

    # A2: security triage. H_A (internal misconfiguration) looks strongest;
    # audit logs at step 3 falsify it. H_B (credential leak) is correct.
    a2_steps = [
        EvidenceStep(
            1,
            {
                "H_A": _branch(0.75, 0.50, 0.75, 0.55, 0.05, 0.30, 0.08),
                "H_B": _branch(0.45, 0.25, 0.80, 0.80, 0.10, 0.60, 0.05),
                "H_C": _branch(0.20, 0.10, 0.65, 0.50, 0.15, 0.85, 0.02),
            },
            note="recent config change looks like the obvious cause",
        ),
        EvidenceStep(
            2,
            {
                "H_A": _branch(0.85, 0.62, 0.75, 0.50, 0.05, 0.18, 0.18),
                "H_B": _branch(0.55, 0.32, 0.80, 0.80, 0.10, 0.50, 0.12),
                "H_C": _branch(0.24, 0.14, 0.65, 0.45, 0.15, 0.82, 0.06),
            },
            note="H_A peak: config change timestamp aligns with first alert",
        ),
        EvidenceStep(
            3,
            {
                "H_A": _branch(0.30, 0.28, 0.75, 0.20, 0.90, 0.70, 0.30),
                "H_B": _branch(0.80, 0.65, 0.80, 0.70, 0.05, 0.25, 0.25),
                "H_C": _branch(0.26, 0.16, 0.65, 0.40, 0.15, 0.80, 0.10),
            },
            note="audit logs show access from outside the config-change window",
        ),
        EvidenceStep(
            4,
            {
                "H_A": _branch(0.20, 0.22, 0.75, 0.10, 0.95, 0.80, 0.38),
                "H_B": _branch(0.95, 0.88, 0.80, 0.30, 0.05, 0.05, 0.40),
                "H_C": _branch(0.22, 0.14, 0.65, 0.30, 0.15, 0.88, 0.14),
            },
            answer_known_from=True,
            note="leaked credential confirmed as entry vector",
        ),
    ]
    scenarios.append(
        Scenario(
            id="falsification-002",
            scenario_type="falsification",
            domain="security-triage",
            prompt=(
                "An alert fires shortly after a configuration change. Audit "
                "logs show logins from outside the change window. Which "
                "hypothesis survives all evidence?"
            ),
            truth_branch="H_B",
            answer="H_B",
            accepted_answers=["H_B", "h_b", "b"],
            decoy_branch="H_A",
            falsified_at_step=3,
            revival_step=None,
            revived_branch=None,
            steps=a2_steps,
            notes="Anchoring trap: recency of the config change explains early confidence, not the cause.",
        )
    )

    # A3: debugging. H_A (obvious library bug) is falsified at step 3 by a
    # minimal reproduction. H_B (caller misuse) is correct.
    a3_steps = [
        EvidenceStep(
            1,
            {
                "H_A": _branch(0.78, 0.48, 0.75, 0.60, 0.05, 0.28, 0.06),
                "H_B": _branch(0.42, 0.22, 0.80, 0.80, 0.10, 0.62, 0.04),
                "H_C": _branch(0.25, 0.12, 0.70, 0.45, 0.12, 0.80, 0.02),
            },
            note="stack trace points at library internals",
        ),
        EvidenceStep(
            2,
            {
                "H_A": _branch(0.86, 0.60, 0.75, 0.55, 0.05, 0.16, 0.16),
                "H_B": _branch(0.52, 0.30, 0.80, 0.78, 0.10, 0.52, 0.10),
                "H_C": _branch(0.28, 0.15, 0.70, 0.42, 0.12, 0.78, 0.06),
            },
            note="library issue tracker has a matching report",
        ),
        EvidenceStep(
            3,
            {
                "H_A": _branch(0.28, 0.26, 0.75, 0.15, 0.90, 0.75, 0.28),
                "H_B": _branch(0.82, 0.68, 0.80, 0.72, 0.05, 0.22, 0.24),
                "H_C": _branch(0.30, 0.17, 0.70, 0.38, 0.12, 0.76, 0.10),
            },
            note="minimal repro without the library also fails",
        ),
        EvidenceStep(
            4,
            {
                "H_A": _branch(0.20, 0.20, 0.75, 0.08, 0.95, 0.85, 0.36),
                "H_B": _branch(0.95, 0.90, 0.80, 0.25, 0.05, 0.05, 0.42),
                "H_C": _branch(0.24, 0.15, 0.70, 0.30, 0.12, 0.86, 0.14),
            },
            answer_known_from=True,
            note="caller passes a mutated default argument; confirmed in isolation",
        ),
    ]
    scenarios.append(
        Scenario(
            id="falsification-003",
            scenario_type="falsification",
            domain="debugging",
            prompt=(
                "A failure's stack trace points inside a third-party library, "
                "but a minimal reproduction without that library also fails. "
                "Which hypothesis survives all evidence?"
            ),
            truth_branch="H_B",
            answer="H_B",
            accepted_answers=["H_B", "h_b", "b"],
            decoy_branch="H_A",
            falsified_at_step=3,
            revival_step=None,
            revived_branch=None,
            steps=a3_steps,
            notes="Confirmation-bias trap: a matching issue-tracker report is not verification.",
        )
    )

    # A4: the decoy is falsified late (step 4), so the wrong answer is already
    # committed for most of the run. H_B is correct.
    a4_steps = [
        EvidenceStep(
            1,
            {
                "H_A": _branch(0.70, 0.42, 0.78, 0.55, 0.05, 0.35, 0.06),
                "H_B": _branch(0.48, 0.28, 0.82, 0.78, 0.08, 0.55, 0.04),
                "H_C": _branch(0.26, 0.16, 0.72, 0.50, 0.10, 0.75, 0.02),
            },
            note="early readout favours the incumbent explanation",
        ),
        EvidenceStep(
            2,
            {
                "H_A": _branch(0.82, 0.58, 0.78, 0.52, 0.05, 0.20, 0.16),
                "H_B": _branch(0.56, 0.34, 0.82, 0.76, 0.08, 0.48, 0.10),
                "H_C": _branch(0.28, 0.18, 0.72, 0.46, 0.10, 0.73, 0.06),
            },
            note="H_A continues to lead on every partial measure",
        ),
        EvidenceStep(
            3,
            {
                "H_A": _branch(0.88, 0.66, 0.78, 0.48, 0.05, 0.14, 0.28),
                "H_B": _branch(0.62, 0.40, 0.82, 0.74, 0.08, 0.42, 0.18),
                "H_C": _branch(0.30, 0.20, 0.72, 0.44, 0.10, 0.71, 0.10),
            },
            note="no disconfirming signal yet; single-hypothesis run would collapse here",
        ),
        EvidenceStep(
            4,
            {
                "H_A": _branch(0.25, 0.24, 0.78, 0.12, 0.92, 0.80, 0.40),
                "H_B": _branch(0.86, 0.74, 0.82, 0.60, 0.05, 0.18, 0.32),
                "H_C": _branch(0.32, 0.22, 0.72, 0.40, 0.10, 0.69, 0.14),
            },
            answer_known_from=True,
            note="decisive measurement arrives late and falsifies H_A",
        ),
        EvidenceStep(
            5,
            {
                "H_A": _branch(0.20, 0.22, 0.78, 0.06, 0.95, 0.88, 0.50),
                "H_B": _branch(0.95, 0.88, 0.82, 0.22, 0.05, 0.05, 0.48),
                "H_C": _branch(0.28, 0.20, 0.72, 0.32, 0.10, 0.78, 0.18),
            },
            answer_known_from=True,
            note="H_B confirmed by an independent method",
        ),
    ]
    scenarios.append(
        Scenario(
            id="falsification-004",
            scenario_type="falsification",
            domain="scientific-reasoning",
            prompt=(
                "An incumbent explanation dominates three successive partial "
                "measurements before a decisive fourth measurement falsifies it. "
                "Which hypothesis survives all evidence?"
            ),
            truth_branch="H_B",
            answer="H_B",
            accepted_answers=["H_B", "h_b", "b"],
            decoy_branch="H_A",
            falsified_at_step=4,
            revival_step=None,
            revived_branch=None,
            steps=a4_steps,
            notes="Late falsification: the wrong hypothesis is strongest for three of five steps.",
        )
    )

    return scenarios


# ---------------------------------------------------------------------------
# Scenario B - revival: a correct hypothesis is rejected/dormant early, then
# materially better evidence must bring it back for the final answer to be right.
# ---------------------------------------------------------------------------
def build_revival_scenarios() -> list[Scenario]:
    scenarios: list[Scenario] = []

    # B1: H_B is correct but appears weak early; step 3 supplies a material
    # evidence increase (>= 0.15) that should revive it.
    b1_steps = [
        EvidenceStep(
            1,
            {
                "H_A": _branch(0.70, 0.45, 0.78, 0.55, 0.05, 0.35, 0.06),
                "H_B": _branch(0.30, 0.20, 0.82, 0.78, 0.20, 0.70, 0.04),
                "H_C": _branch(0.24, 0.14, 0.72, 0.50, 0.12, 0.78, 0.02),
            },
            note="H_B has high information gain but weak current evidence",
        ),
        EvidenceStep(
            2,
            {
                "H_A": _branch(0.80, 0.55, 0.78, 0.50, 0.05, 0.22, 0.16),
                "H_B": _branch(0.25, 0.18, 0.82, 0.78, 0.25, 0.78, 0.10),
                "H_C": _branch(0.26, 0.15, 0.72, 0.46, 0.12, 0.76, 0.06),
            },
            note="H_B drifts below the dormant score threshold",
        ),
        EvidenceStep(
            3,
            {
                "H_A": _branch(0.78, 0.55, 0.78, 0.45, 0.10, 0.25, 0.28),
                "H_B": _branch(0.55, 0.30, 0.82, 0.75, 0.10, 0.50, 0.24),
                "H_C": _branch(0.25, 0.15, 0.72, 0.44, 0.12, 0.78, 0.10),
            },
            note="new instrument measures the effect H_B predicts (revival signal)",
        ),
        EvidenceStep(
            4,
            {
                "H_A": _branch(0.60, 0.45, 0.78, 0.35, 0.20, 0.35, 0.38),
                "H_B": _branch(0.85, 0.70, 0.82, 0.50, 0.05, 0.20, 0.36),
                "H_C": _branch(0.25, 0.15, 0.72, 0.38, 0.12, 0.80, 0.14),
            },
            answer_known_from=True,
            note="H_B now leads; H_A unresolved",
        ),
        EvidenceStep(
            5,
            {
                "H_A": _branch(0.45, 0.35, 0.78, 0.25, 0.30, 0.45, 0.48),
                "H_B": _branch(0.95, 0.88, 0.82, 0.20, 0.05, 0.05, 0.50),
                "H_C": _branch(0.24, 0.14, 0.72, 0.30, 0.12, 0.85, 0.18),
            },
            answer_known_from=True,
            note="H_B confirmed",
        ),
    ]
    scenarios.append(
        Scenario(
            id="revival-001",
            scenario_type="revival",
            domain="scientific-reasoning",
            prompt=(
                "One hypothesis looks weak early but a new instrument later "
                "measures exactly the effect it predicts. Which hypothesis "
                "survives all evidence?"
            ),
            truth_branch="H_B",
            answer="H_B",
            accepted_answers=["H_B", "h_b", "b"],
            decoy_branch=None,
            falsified_at_step=None,
            revival_step=3,
            revived_branch="H_B",
            steps=b1_steps,
            notes="Correct hypothesis goes dormant at step 2 and must be revived at step 3.",
        )
    )

    # B2: H_C is correct. It is weakest at steps 1-2, then verification rises
    # by >= 0.25 at step 3 (independent cross-check) which should revive it.
    b2_steps = [
        EvidenceStep(
            1,
            {
                "H_A": _branch(0.74, 0.48, 0.76, 0.55, 0.05, 0.32, 0.06),
                "H_B": _branch(0.55, 0.35, 0.80, 0.70, 0.08, 0.45, 0.05),
                "H_C": _branch(0.28, 0.18, 0.85, 0.82, 0.10, 0.72, 0.03),
            },
            note="H_C is independent and high-value but unverified",
        ),
        EvidenceStep(
            2,
            {
                "H_A": _branch(0.82, 0.58, 0.76, 0.50, 0.05, 0.20, 0.16),
                "H_B": _branch(0.58, 0.38, 0.80, 0.68, 0.08, 0.42, 0.11),
                "H_C": _branch(0.24, 0.14, 0.85, 0.82, 0.12, 0.80, 0.07),
            },
            note="H_C falls dormant",
        ),
        EvidenceStep(
            3,
            {
                "H_A": _branch(0.80, 0.58, 0.76, 0.45, 0.05, 0.22, 0.28),
                "H_B": _branch(0.56, 0.36, 0.80, 0.65, 0.08, 0.45, 0.20),
                "H_C": _branch(0.50, 0.45, 0.85, 0.80, 0.08, 0.55, 0.22),
            },
            note="an independent method reproduces the H_C prediction (verification jump)",
        ),
        EvidenceStep(
            4,
            {
                "H_A": _branch(0.62, 0.48, 0.76, 0.35, 0.15, 0.32, 0.38),
                "H_B": _branch(0.52, 0.34, 0.80, 0.60, 0.10, 0.50, 0.32),
                "H_C": _branch(0.82, 0.75, 0.85, 0.55, 0.05, 0.20, 0.36),
            },
            answer_known_from=True,
            note="H_C leads after revival",
        ),
        EvidenceStep(
            5,
            {
                "H_A": _branch(0.50, 0.40, 0.76, 0.25, 0.22, 0.40, 0.48),
                "H_B": _branch(0.48, 0.32, 0.80, 0.55, 0.12, 0.55, 0.42),
                "H_C": _branch(0.93, 0.90, 0.85, 0.22, 0.05, 0.05, 0.50),
            },
            answer_known_from=True,
            note="H_C confirmed",
        ),
    ]
    scenarios.append(
        Scenario(
            id="revival-002",
            scenario_type="revival",
            domain="cross-domain",
            prompt=(
                "The correct explanation is initially the weakest of three and "
                "later gains independent verification. Which hypothesis "
                "survives all evidence?"
            ),
            truth_branch="H_C",
            answer="H_C",
            accepted_answers=["H_C", "h_c", "c"],
            decoy_branch=None,
            falsified_at_step=None,
            revival_step=3,
            revived_branch="H_C",
            steps=b2_steps,
            notes="Correct hypothesis goes dormant at step 2; verification jump at step 3 is the revival signal.",
        )
    )

    # B3: rejected-then-reopened. H_C reaches contradiction >= 0.85 at step 2 on
    # evidence that is itself invalidated at step 3, so an explicit reopen must
    # be triggered. H_C is correct.
    b3_steps = [
        EvidenceStep(
            1,
            {
                "H_A": _branch(0.72, 0.48, 0.78, 0.55, 0.05, 0.30, 0.06),
                "H_B": _branch(0.50, 0.32, 0.80, 0.70, 0.08, 0.45, 0.05),
                "H_C": _branch(0.45, 0.28, 0.85, 0.80, 0.10, 0.55, 0.03),
            },
            note="all three hypotheses still open",
        ),
        EvidenceStep(
            2,
            {
                "H_A": _branch(0.80, 0.56, 0.78, 0.50, 0.05, 0.20, 0.16),
                "H_B": _branch(0.52, 0.34, 0.80, 0.68, 0.08, 0.43, 0.11),
                "H_C": _branch(0.30, 0.22, 0.85, 0.80, 0.90, 0.70, 0.08),
            },
            note="H_C is rejected on a reported conflicting observation",
        ),
        EvidenceStep(
            3,
            {
                "H_A": _branch(0.78, 0.56, 0.78, 0.45, 0.05, 0.22, 0.28),
                "H_B": _branch(0.54, 0.36, 0.80, 0.66, 0.08, 0.42, 0.20),
                "H_C": _branch(0.55, 0.40, 0.85, 0.80, 0.10, 0.45, 0.24),
            },
            note="the conflicting observation is itself retracted as invalid",
        ),
        EvidenceStep(
            4,
            {
                "H_A": _branch(0.62, 0.48, 0.78, 0.35, 0.12, 0.32, 0.38),
                "H_B": _branch(0.52, 0.34, 0.80, 0.62, 0.10, 0.45, 0.32),
                "H_C": _branch(0.85, 0.75, 0.85, 0.55, 0.05, 0.18, 0.38),
            },
            answer_known_from=True,
            note="H_C reopened and now leads",
        ),
        EvidenceStep(
            5,
            {
                "H_A": _branch(0.50, 0.42, 0.78, 0.25, 0.20, 0.40, 0.48),
                "H_B": _branch(0.48, 0.32, 0.80, 0.58, 0.12, 0.50, 0.42),
                "H_C": _branch(0.93, 0.90, 0.85, 0.22, 0.05, 0.05, 0.50),
            },
            answer_known_from=True,
            note="H_C confirmed after reopening",
        ),
    ]
    scenarios.append(
        Scenario(
            id="revival-003",
            scenario_type="revival",
            domain="evidence-handling",
            prompt=(
                "A hypothesis is rejected on a conflicting observation that is "
                "later retracted as invalid. Which hypothesis survives all "
                "evidence?"
            ),
            truth_branch="H_C",
            answer="H_C",
            accepted_answers=["H_C", "h_c", "c"],
            decoy_branch=None,
            falsified_at_step=None,
            revival_step=3,
            revived_branch="H_C",
            steps=b3_steps,
            notes=(
                "Rejected-branch reopen: the reference controller does not auto-revive "
                "rejected branches, so the runner must explicitly reopen H_C when its "
                "rejection premise is invalidated."
            ),
        )
    )

    return scenarios


# ---------------------------------------------------------------------------
# Scenario C - control: the first/leading hypothesis is correct throughout.
# ---------------------------------------------------------------------------
def build_control_scenarios() -> list[Scenario]:
    scenarios: list[Scenario] = []

    c1_steps = [
        EvidenceStep(
            1,
            {
                "H_A": _branch(0.70, 0.45, 0.78, 0.55, 0.05, 0.32, 0.06),
                "H_B": _branch(0.42, 0.24, 0.82, 0.70, 0.08, 0.58, 0.04),
                "H_C": _branch(0.24, 0.14, 0.72, 0.48, 0.10, 0.76, 0.02),
            },
            answer_known_from=True,
            note="initial ranking already matches ground truth",
        ),
        EvidenceStep(
            2,
            {
                "H_A": _branch(0.82, 0.60, 0.78, 0.48, 0.05, 0.18, 0.16),
                "H_B": _branch(0.45, 0.26, 0.82, 0.68, 0.08, 0.55, 0.10),
                "H_C": _branch(0.26, 0.15, 0.72, 0.45, 0.10, 0.74, 0.06),
            },
            answer_known_from=True,
            note="lead consolidated",
        ),
        EvidenceStep(
            3,
            {
                "H_A": _branch(0.88, 0.70, 0.78, 0.40, 0.05, 0.12, 0.28),
                "H_B": _branch(0.44, 0.26, 0.82, 0.62, 0.08, 0.55, 0.18),
                "H_C": _branch(0.25, 0.14, 0.72, 0.42, 0.10, 0.75, 0.10),
            },
            answer_known_from=True,
            note="lead further consolidated",
        ),
        EvidenceStep(
            4,
            {
                "H_A": _branch(0.95, 0.85, 0.78, 0.20, 0.05, 0.05, 0.40),
                "H_B": _branch(0.42, 0.24, 0.82, 0.55, 0.08, 0.58, 0.26),
                "H_C": _branch(0.24, 0.13, 0.72, 0.38, 0.10, 0.78, 0.14),
            },
            answer_known_from=True,
            note="verified",
        ),
    ]
    scenarios.append(
        Scenario(
            id="control-001",
            scenario_type="control",
            domain="diagnosis",
            prompt=(
                "The initially strongest hypothesis is confirmed by every "
                "subsequent check. Which hypothesis survives all evidence?"
            ),
            truth_branch="H_A",
            answer="H_A",
            accepted_answers=["H_A", "h_a", "a"],
            decoy_branch=None,
            falsified_at_step=None,
            revival_step=None,
            revived_branch=None,
            steps=c1_steps,
            notes="Control: correct answer is the leader from the first step.",
        )
    )

    c2_steps = [
        EvidenceStep(
            1,
            {
                "H_A": _branch(0.68, 0.42, 0.75, 0.55, 0.05, 0.35, 0.05),
                "H_B": _branch(0.55, 0.34, 0.80, 0.72, 0.08, 0.45, 0.04),
                "H_C": _branch(0.30, 0.18, 0.72, 0.55, 0.12, 0.70, 0.02),
            },
            answer_known_from=True,
            note="H_A leads from the start",
        ),
        EvidenceStep(
            2,
            {
                "H_A": _branch(0.80, 0.58, 0.75, 0.50, 0.05, 0.20, 0.15),
                "H_B": _branch(0.58, 0.36, 0.80, 0.70, 0.08, 0.42, 0.10),
                "H_C": _branch(0.32, 0.19, 0.72, 0.52, 0.12, 0.68, 0.06),
            },
            answer_known_from=True,
            note="no contradiction appears at any point",
        ),
        EvidenceStep(
            3,
            {
                "H_A": _branch(0.86, 0.68, 0.75, 0.42, 0.05, 0.14, 0.27),
                "H_B": _branch(0.56, 0.35, 0.80, 0.66, 0.08, 0.44, 0.18),
                "H_C": _branch(0.30, 0.18, 0.72, 0.50, 0.12, 0.70, 0.10),
            },
            answer_known_from=True,
            note="alternatives remain weak and unresolved",
        ),
    ]
    scenarios.append(
        Scenario(
            id="control-002",
            scenario_type="control",
            domain="planning",
            prompt=(
                "The leading plan is validated at every checkpoint and no "
                "contradiction is ever observed. Which hypothesis survives all "
                "evidence?"
            ),
            truth_branch="H_A",
            answer="H_A",
            accepted_answers=["H_A", "h_a", "a"],
            decoy_branch=None,
            falsified_at_step=None,
            revival_step=None,
            revived_branch=None,
            steps=c2_steps,
            notes="Control: stable leader, no falsification event.",
        )
    )

    return scenarios


def build_all_scenarios() -> list[Scenario]:
    """Return the full deterministic scenario set (documented order)."""
    return build_falsification_scenarios() + build_revival_scenarios() + build_control_scenarios()


def scenario_as_case_record(scenario: Scenario) -> dict[str, Any]:
    """Convert a scenario into a `benchmark/cases.jsonl`-compatible record."""
    return {
        "id": scenario.id,
        "domain": scenario.domain,
        "prompt": scenario.prompt,
        "accepted_answers": list(scenario.accepted_answers),
        "scenario_type": scenario.scenario_type,
        "notes": scenario.notes,
    }


def scenario_to_dict(scenario: Scenario) -> dict[str, Any]:
    payload = asdict(scenario)
    payload["steps"] = [asdict(step) for step in scenario.steps]
    return payload


def scenarios_to_dict(scenarios: list[Scenario]) -> list[dict[str, Any]]:
    return [scenario_to_dict(scenario) for scenario in scenarios]
