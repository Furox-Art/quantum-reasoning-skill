from qreason import Branch, EngineConfig, Evaluation, QuantumReasoningEngine


def generator(problem: str, parent: Branch | None, n: int) -> list[str]:
    if parent is None:
        return ["alpha", "beta", "gamma", "alpha"][:n]
    return [f"{parent.text}-{i}" for i in range(n)]


def evaluator(problem: str, branch: Branch, peers: tuple[Branch, ...]) -> Evaluation:
    base = 0.9 if branch.text.startswith("alpha") else 0.6
    return Evaluation(
        confidence=base,
        verification=base,
        novelty=0.7,
        information_gain=0.7,
        contradiction_penalty=0.0,
    )


def test_probabilities_sum_to_one() -> None:
    engine = QuantumReasoningEngine(
        EngineConfig(initial_branches=3, max_depth=0, min_survivors=1)
    )
    result = engine.run("test", generator, evaluator)
    total = sum(branch.probability for branch in result.survivors)
    assert abs(total - 1.0) < 1e-9


def test_duplicate_initial_branches_are_removed() -> None:
    engine = QuantumReasoningEngine(
        EngineConfig(initial_branches=4, max_depth=0, min_survivors=3, prune_ratio=0.0)
    )
    result = engine.run("test", generator, evaluator)
    assert result.total_generated == 3
    assert len({branch.text for branch in result.survivors}) == 3


def test_higher_verified_branch_ranks_first() -> None:
    engine = QuantumReasoningEngine(
        EngineConfig(initial_branches=3, max_depth=0, min_survivors=1)
    )
    result = engine.run("test", generator, evaluator)
    assert result.survivors[0].text == "alpha"


def test_compute_budget_is_respected() -> None:
    engine = QuantumReasoningEngine(
        EngineConfig(
            initial_branches=3,
            min_children=3,
            max_children=3,
            max_depth=5,
            max_total_generated=8,
            min_survivors=1,
        )
    )
    result = engine.run("test", generator, evaluator)
    assert result.total_generated <= 8


def test_empty_problem_is_rejected() -> None:
    engine = QuantumReasoningEngine()
    try:
        engine.run("   ", generator, evaluator)
    except ValueError as exc:
        assert "problem" in str(exc)
    else:
        raise AssertionError("Expected ValueError")
