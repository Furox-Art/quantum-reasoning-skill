from __future__ import annotations

from .core import Branch, Evaluation, QuantumReasoningEngine


def demo_generator(problem: str, parent: Branch | None, n: int) -> list[str]:
    if parent is None:
        seeds = [
            "Direct solution hypothesis",
            "Constraint-first analysis",
            "Counterexample search",
            "Tool-verification strategy",
            "Alternative-model hypothesis",
            "Failure-mode analysis",
        ]
        return seeds[:n]

    continuations = [
        "test with an executable check",
        "search for a contradiction",
        "derive consequences from constraints",
        "compare against an independent alternative",
    ]
    return [f"{parent.text} -> {step}" for step in continuations[:n]]


def demo_evaluator(problem: str, branch: Branch, peers: tuple[Branch, ...]) -> Evaluation:
    text = branch.text.lower()
    verification = 0.9 if ("test" in text or "verification" in text) else 0.55
    information_gain = 0.85 if ("counterexample" in text or "constraint" in text) else 0.60
    novelty = 0.80 if branch.depth == 0 else 0.65
    confidence = 0.70 if "direct" in text else 0.62
    contradiction_penalty = 0.05 if "contradiction" in text else 0.0
    return Evaluation(
        confidence=confidence,
        verification=verification,
        novelty=novelty,
        information_gain=information_gain,
        contradiction_penalty=contradiction_penalty,
    )


def demo_merger(problem: str, survivors: tuple[Branch, ...]) -> str:
    best = max(survivors, key=lambda b: b.score)
    return f"Selected path: {best.text}"


def main() -> None:
    engine = QuantumReasoningEngine()
    result = engine.run(
        "Choose a robust reasoning strategy.",
        demo_generator,
        demo_evaluator,
        demo_merger,
    )
    print(result.answer)
    print(f"rounds={result.rounds} generated={result.total_generated}")
    print("survivors:")
    for branch in result.survivors:
        print(
            f"  p={branch.probability:.3f} score={branch.score:.3f} "
            f"depth={branch.depth} | {branch.text}"
        )


if __name__ == "__main__":
    main()
