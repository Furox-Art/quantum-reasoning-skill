from __future__ import annotations

from dataclasses import dataclass, field
from math import ceil, exp, log, sqrt
from typing import Any, Callable, Optional, Sequence


@dataclass(frozen=True)
class Evaluation:
    confidence: float = 0.5
    verification: float = 0.5
    novelty: float = 0.5
    information_gain: float = 0.5
    contradiction_penalty: float = 0.0

    def clamped(self) -> "Evaluation":
        def c(value: float) -> float:
            return max(0.0, min(1.0, float(value)))

        return Evaluation(
            confidence=c(self.confidence),
            verification=c(self.verification),
            novelty=c(self.novelty),
            information_gain=c(self.information_gain),
            contradiction_penalty=c(self.contradiction_penalty),
        )


@dataclass
class Branch:
    id: int
    text: str
    parent_id: Optional[int]
    depth: int
    evaluation: Evaluation = field(default_factory=Evaluation)
    score: float = 0.0
    probability: float = 0.0
    amplitude: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class EngineConfig:
    initial_branches: int = 6
    min_children: int = 1
    max_children: int = 4
    max_depth: int = 3
    max_live_branches: int = 12
    max_total_generated: int = 64
    prune_ratio: float = 0.5
    min_survivors: int = 2
    temperature: float = 0.7

    confidence_weight: float = 0.25
    verification_weight: float = 0.30
    novelty_weight: float = 0.15
    information_gain_weight: float = 0.20
    contradiction_weight: float = 0.30


@dataclass
class ReasoningResult:
    answer: str
    survivors: list[Branch]
    archive: list[Branch]
    rounds: int
    total_generated: int


Generator = Callable[[str, Optional[Branch], int], Sequence[str]]
Evaluator = Callable[[str, Branch, Sequence[Branch]], Evaluation]
Merger = Callable[[str, Sequence[Branch]], str]


class QuantumReasoningEngine:
    """Classical, quantum-inspired orchestration for multi-branch reasoning."""

    def __init__(self, config: Optional[EngineConfig] = None) -> None:
        self.config = config or EngineConfig()
        self._next_id = 0
        self._validate_config()

    def _validate_config(self) -> None:
        c = self.config
        if c.initial_branches < 1:
            raise ValueError("initial_branches must be >= 1")
        if c.min_children < 1 or c.max_children < c.min_children:
            raise ValueError("children bounds are invalid")
        if c.max_depth < 0:
            raise ValueError("max_depth must be >= 0")
        if c.max_live_branches < 1 or c.max_total_generated < 1:
            raise ValueError("branch budgets must be >= 1")
        if not 0.0 <= c.prune_ratio < 1.0:
            raise ValueError("prune_ratio must be in [0, 1)")
        if c.min_survivors < 1:
            raise ValueError("min_survivors must be >= 1")
        if c.temperature <= 0:
            raise ValueError("temperature must be > 0")

    @staticmethod
    def _canonical(text: str) -> str:
        return " ".join(text.lower().split())

    def _new_branch(self, text: str, parent: Optional[Branch], depth: int) -> Branch:
        branch = Branch(
            id=self._next_id,
            text=text.strip(),
            parent_id=None if parent is None else parent.id,
            depth=depth,
        )
        self._next_id += 1
        return branch

    def _score(self, evaluation: Evaluation) -> float:
        c = self.config
        e = evaluation.clamped()
        return (
            e.confidence * c.confidence_weight
            + e.verification * c.verification_weight
            + e.novelty * c.novelty_weight
            + e.information_gain * c.information_gain_weight
            - e.contradiction_penalty * c.contradiction_weight
        )

    def _evaluate(self, problem: str, branches: list[Branch], evaluator: Evaluator) -> None:
        snapshot = tuple(branches)
        for branch in branches:
            branch.evaluation = evaluator(problem, branch, snapshot).clamped()
            branch.score = self._score(branch.evaluation)
        self._normalize(branches)

    def _normalize(self, branches: list[Branch]) -> None:
        if not branches:
            return
        temperature = self.config.temperature
        peak = max(branch.score for branch in branches)
        exps = [exp((branch.score - peak) / temperature) for branch in branches]
        total = sum(exps) or 1.0
        for branch, value in zip(branches, exps):
            branch.probability = value / total
            # A quantum-inspired representation only: this is not a quantum amplitude.
            branch.amplitude = sqrt(branch.probability)

    @staticmethod
    def _normalized_entropy(branches: Sequence[Branch]) -> float:
        if len(branches) <= 1:
            return 0.0
        entropy = -sum(
            branch.probability * log(branch.probability)
            for branch in branches
            if branch.probability > 0.0
        )
        return max(0.0, min(1.0, entropy / log(len(branches))))

    def _adaptive_children(self, branches: list[Branch]) -> int:
        self._normalize(branches)
        uncertainty = self._normalized_entropy(branches)
        span = self.config.max_children - self.config.min_children
        return self.config.min_children + round(uncertainty * span)

    def _prune(self, branches: list[Branch]) -> tuple[list[Branch], list[Branch]]:
        if not branches:
            return [], []
        ordered = sorted(branches, key=lambda b: (b.score, b.probability), reverse=True)
        keep_by_ratio = ceil(len(ordered) * (1.0 - self.config.prune_ratio))
        keep = max(self.config.min_survivors, keep_by_ratio)
        keep = min(keep, self.config.max_live_branches, len(ordered))
        survivors = ordered[:keep]
        discarded = ordered[keep:]
        self._normalize(survivors)
        return survivors, discarded

    def run(
        self,
        problem: str,
        generator: Generator,
        evaluator: Evaluator,
        merger: Optional[Merger] = None,
    ) -> ReasoningResult:
        if not problem.strip():
            raise ValueError("problem cannot be empty")

        self._next_id = 0
        archive: list[Branch] = []
        seen: set[str] = set()
        total_generated = 0

        initial_texts = generator(problem, None, self.config.initial_branches)
        branches: list[Branch] = []
        for text in initial_texts:
            if total_generated >= self.config.max_total_generated:
                break
            if not text or not text.strip():
                continue
            key = self._canonical(text)
            if key in seen:
                continue
            seen.add(key)
            branches.append(self._new_branch(text, None, 0))
            total_generated += 1

        if not branches:
            raise ValueError("generator produced no usable initial branches")

        self._evaluate(problem, branches, evaluator)
        rounds = 1

        for depth in range(1, self.config.max_depth + 1):
            survivors, discarded = self._prune(branches)
            archive.extend(discarded)

            remaining_budget = self.config.max_total_generated - total_generated
            if remaining_budget <= 0:
                branches = survivors
                break

            child_count = self._adaptive_children(survivors)
            children: list[Branch] = []

            for parent in survivors:
                remaining_budget = self.config.max_total_generated - total_generated
                if remaining_budget <= 0:
                    break
                request_n = min(child_count, remaining_budget)
                for text in generator(problem, parent, request_n):
                    if total_generated >= self.config.max_total_generated:
                        break
                    if not text or not text.strip():
                        continue
                    key = self._canonical(text)
                    if key in seen:
                        continue
                    seen.add(key)
                    children.append(self._new_branch(text, parent, depth))
                    total_generated += 1

            if not children:
                branches = survivors
                break

            branches = survivors + children
            self._evaluate(problem, branches, evaluator)
            rounds += 1

        survivors, discarded = self._prune(branches)
        archive.extend(discarded)
        self._normalize(survivors)

        if merger is None:
            answer = survivors[0].text
        else:
            answer = merger(problem, tuple(survivors))

        return ReasoningResult(
            answer=answer,
            survivors=survivors,
            archive=archive,
            rounds=rounds,
            total_generated=total_generated,
        )
