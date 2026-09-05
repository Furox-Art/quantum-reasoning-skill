from qreason import Branch, EngineConfig, Evaluation, QuantumReasoningEngine


config = EngineConfig(
    initial_branches=4,
    min_children=1,
    max_children=3,
    max_depth=2,
    max_total_generated=24,
)
engine = QuantumReasoningEngine(config)


def generate(problem: str, parent: Branch | None, n: int) -> list[str]:
    if parent is None:
        options = [
            "Solve directly",
            "Search for a counterexample",
            "Reduce to simpler subproblems",
            "Verify assumptions first",
        ]
    else:
        options = [
            f"{parent.text} -> numerical check",
            f"{parent.text} -> independent derivation",
            f"{parent.text} -> adversarial check",
        ]
    return options[:n]


def evaluate(problem: str, branch: Branch, peers: tuple[Branch, ...]) -> Evaluation:
    text = branch.text.lower()
    return Evaluation(
        confidence=0.75 if "direct" in text else 0.65,
        verification=0.95 if "check" in text or "verify" in text else 0.55,
        novelty=0.80,
        information_gain=0.90 if "counterexample" in text else 0.70,
        contradiction_penalty=0.0,
    )


def merge(problem: str, survivors: tuple[Branch, ...]) -> str:
    best = max(survivors, key=lambda branch: branch.score)
    return best.text


result = engine.run(
    "Find the most reliable way to solve this problem.",
    generate,
    evaluate,
    merge,
)

print(result.answer)
for branch in result.survivors:
    print(branch.probability, branch.text)
