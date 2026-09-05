# Quantum Reasoning Skill

A **quantum-inspired, model-agnostic reasoning skill** for exploring multiple competing solution paths instead of committing to one path too early.

> This project does **not** perform quantum computation. It borrows ideas such as maintaining multiple possibilities, weighted states, interference-like comparison, and collapse-like selection, and implements them on classical hardware.

## Core idea

```text
problem
  -> generate diverse branches
  -> score each branch
  -> normalize probability weights
  -> compare / verify / detect contradictions
  -> prune weak branches
  -> spend more compute on uncertain or promising branches
  -> merge the strongest surviving evidence
  -> final answer
```

## Goals

- Keep several plausible hypotheses alive at once.
- Prevent early lock-in to the first reasonable answer.
- Force branch diversity rather than producing near-duplicates.
- Allocate more compute when uncertainty is high.
- Support external verifiers, tools, tests, solvers, or other models.
- Stay independent of any single LLM provider.

## What is implemented

- Probabilistic branch weighting using softmax.
- Confidence, verification, novelty, information-gain, and contradiction signals.
- Entropy-based adaptive branching.
- Duplicate branch suppression.
- Beam-style pruning with a configurable compute budget.
- Final merge hook for an LLM or deterministic aggregator.
- A reusable `SKILL.md` instruction layer.
- Pure-Python reference engine with no runtime dependencies.
- Unit tests and CI.

## Install

```bash
git clone https://github.com/Furox-Art/quantum-reasoning-skill.git
cd quantum-reasoning-skill
pip install -e .
```

## Run the deterministic demo

```bash
qreason-demo
```

or:

```bash
python examples/basic.py
```

## Use with any model

Implement three small callbacks:

```python
from qreason import Evaluation, QuantumReasoningEngine

engine = QuantumReasoningEngine()


def generate(problem, parent, n):
    # Ask your model for n genuinely different hypotheses / continuations.
    ...


def evaluate(problem, candidate, peers):
    # May call another model, tests, Python, a solver, search, etc.
    return Evaluation(
        confidence=0.8,
        verification=0.9,
        novelty=0.7,
        information_gain=0.8,
        contradiction_penalty=0.0,
    )


def merge(problem, survivors):
    # Ask the model to synthesize only from the strongest verified branches.
    ...

result = engine.run(problem, generate, evaluate, merge)
print(result.answer)
```

## Scoring

Each branch receives a classical score:

```text
score =
    confidence*w1
  + verification*w2
  + novelty*w3
  + information_gain*w4
  - contradiction_penalty*w5
```

Scores become normalized probability weights. Their entropy controls how broadly the next round explores: high uncertainty opens more branches; low uncertainty concentrates compute.

## Repository layout

```text
SKILL.md                  Model-facing reasoning protocol
src/qreason/core.py       Reference branching engine
src/qreason/cli.py        Deterministic demo CLI
examples/basic.py         Minimal integration example
tests/test_core.py        Unit tests
.github/workflows/test.yml CI
```

## Status

**v0.1 prototype.** The current engine establishes the orchestration layer. Next stages can add semantic diversity metrics, branch revival, learned routing, tool-aware verification, parallel execution, and benchmark evaluation against single-path reasoning.
