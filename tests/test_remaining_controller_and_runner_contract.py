"""Adversarial decisions and edge metrics for falsification and controller."""

from __future__ import annotations

from dataclasses import replace

import pytest

from benchmark.falsification import run_suite as runner
from benchmark.falsification import scenarios as src
from reference import branch_controller as bc


def _metrics(*, evidence=1.0, verification=1.0, contradiction=0.0, information_gain=0.8):
    return bc.BranchMetrics(
        evidence=evidence,
        verification=verification,
        independence=1.0,
        information_gain=information_gain,
        contradiction=contradiction,
        unresolved_assumptions=0.0,
        normalized_cost=0.0,
    )


def _branch(name, **kwargs):
    return bc.Branch(name, _metrics(**kwargs))


def test_entropy_nonfinite_negative_and_zero_cases() -> None:
    assert bc.normalized_entropy([]) == 0.0
    assert bc.normalized_entropy([0, 0]) == 0.0
    assert bc.normalized_entropy([0, 1]) == 0.0
    assert bc.normalized_entropy([1, 1]) == pytest.approx(1.0)
    with pytest.raises(ValueError, match="finite and non-negative"):
        bc.normalized_entropy([-0.1, 1])
    with pytest.raises(ValueError, match="probability total must be finite"):
        bc.normalized_entropy([1e308, 1e308])
    assert (
        bc.uncertainty_from_branches(
            [
                replace(_branch("a"), state=bc.BranchState.REJECTED),
            ]
        )
        == 0.0
    )


@pytest.mark.parametrize("entropy", [-0.01, 1.01, float("nan")])
def test_width_rejects_invalid_probability(entropy):
    with pytest.raises(ValueError, match="uncertainty must be"):
        bc.recommended_width(entropy)


def test_diversity_has_independent_input_validation() -> None:
    assert bc.diversity_ratio([]) == 1.0
    assert bc.diversity_ratio([0.0, 0.90], duplicate_threshold=0.85) == 0.5
    for value, threshold in (([0.2], -0.1), ([0.2], 1.1), ([-0.1], 0.8), ([1.1], 0.8)):
        with pytest.raises(ValueError):
            bc.diversity_ratio(value, duplicate_threshold=threshold)


def test_collapse_guards_ordered_by_specificity() -> None:
    empty = bc.collapse_decision([])
    assert empty[0] is False and "no surviving branch" in empty[1]
    leader = _branch("leader")
    assert bc.collapse_decision([leader])[0] is True
    if not (bc.branch_score(leader.metrics) >= bc.DEFAULT_THRESHOLDS.collapse_score):
        pytest.fail("Expected high-quality synthetic leader to pass collapse threshold")

    weak = replace(leader, metrics=_metrics(evidence=0, verification=0))
    assert "score" in bc.collapse_decision([weak])[1]

    thresholds = replace(bc.DEFAULT_THRESHOLDS, collapse_score=0.0)
    unverified = replace(leader, metrics=_metrics(verification=0.1))
    assert "verification" in bc.collapse_decision([unverified], thresholds)[1]

    contradicted = replace(leader, metrics=_metrics(contradiction=0.3))
    assert "contradiction" in bc.collapse_decision([contradicted], thresholds)[1]

    near = _branch("near", evidence=0.99)
    assert "high-information" in bc.collapse_decision([leader, near])[1]
    near = _branch("near", evidence=0.99, information_gain=0.2)
    assert "margin" in bc.collapse_decision([leader, near])[1]


def test_revival_evidence_and_rejection_guards() -> None:
    dormant = replace(
        _branch("dormant", evidence=0.8),
        state=bc.BranchState.DORMANT,
        previous_metrics=_metrics(evidence=0.5, verification=0.9),
    )
    assert bc.should_revive(dormant)
    assert bc.update_branch_state(dormant).state == bc.BranchState.ACTIVE
    assert not bc.should_revive(replace(dormant, previous_metrics=None))
    assert not bc.should_revive(replace(dormant, state=bc.BranchState.REJECTED))
    assert (
        bc.classify_branch(_branch("rejected", contradiction=1.0)).state == bc.BranchState.REJECTED
    )


def test_runner_report_handles_unusual_but_valid_synthetic_scenarios() -> None:
    source = src.build_all_scenarios()[0]
    # A truth branch is not necessarily falsified; measure latency/delay even
    # if the benchmark's decoy is not the initially selected leader.
    altered = replace(source, decoy_branch="not-in-metrics")
    result = runner._run_single_policy(altered)
    assert result.switch_success is True
    assert result.switch_delay_steps == 0

    # When no evidence step allows a committed decision, all probabilities
    # remain unscored, rather than reporting invented calibration scores.
    altered = replace(
        source,
        decoy_branch=None,
        steps=[replace(step, answer_known_from=False) for step in source.steps],
    )
    single = runner._run_single_policy(altered)
    multi = runner._run_multi_policy(altered)
    assert single.brier is None
    assert multi.brier is None
    assert not single.probability_rows and not multi.probability_rows


def test_controller_surviving_leader_and_falsification_failure_metadata() -> None:
    source = src.build_all_scenarios()[0]
    # Decoy never crosses the falsification threshold: "no switch event"
    # must remain None instead of an invented success.
    nonevent = replace(source, decoy_branch="absent")
    outcome = runner._run_multi_policy(nonevent)
    assert outcome.switch_success is None
    assert outcome.switch_delay_steps is None

    # High contradiction on decoy but wrong surviving leader: preserves failure.
    wrong = replace(source, truth_branch="does_not_exist")
    outcome = runner._run_multi_policy(wrong)
    assert outcome.correct is False
    assert outcome.switch_success is False


def test_brier_and_reliability_empty_bounds():
    assert runner._brier_from_rows([]) == 0.0
    assert runner.reliability_rows([]) == []
    sample = runner._run_multi_policy(src.build_all_scenarios()[0])
    invalid = replace(
        sample,
        probability_rows=[
            {"truth": "truth", "step": 1, "probabilities": {"truth": 1.2}},
        ],
    )
    assert runner.reliability_rows([invalid])[0]["bin"] == "0.8-1.0"


def test_scenario_to_dictionary_roundtrip_preserves_steps():
    scenarios = src.build_all_scenarios()
    objects = src.scenarios_to_dict(scenarios)
    assert len(objects) == len(scenarios)
    assert objects[0] == src.scenario_to_dict(scenarios[0])
    assert objects[0]["steps"][0]["step"] == scenarios[0].steps[0].step


def test_entropy_classification_works_without_assuming_probability_scale():
    assert bc.recommended_width(0.1) == (2, 3)
    assert bc.recommended_width(0.4) == (4, 6)
    assert bc.recommended_width(0.9) == (6, 10)
