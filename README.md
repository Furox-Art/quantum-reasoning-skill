# Quantum Reasoning Skill

A **model-agnostic reasoning skill** that keeps multiple genuinely different possibilities alive, verifies and compares them, suppresses weak paths, revives useful alternatives when evidence changes, and selects the best-supported result only at the end.

> This is quantum-inspired classical reasoning, not quantum computation.

## Main artifact

The project is centered on [`SKILL.md`](./SKILL.md). The skill changes the model's reasoning procedure without retraining the model.

```text
problem
  -> open diverse possibilities
  -> verify independently
  -> compare contradictions and shared assumptions
  -> allocate compute dynamically
  -> prune / suspend weak branches
  -> revive branches when evidence changes
  -> final verification
  -> collapse to the best-supported answer
```

## Design goals

- Reduce early lock-in to the first plausible answer.
- Maintain genuinely independent hypotheses or solution strategies.
- Prefer falsification and tool-based verification over self-confidence.
- Expand search when uncertainty is high and concentrate compute when evidence is strong.
- Detect correlated branches so repeated assumptions are not counted as independent evidence.
- Keep high-information alternatives recoverable instead of deleting them too early.
- Work across models and providers that support instruction-following skills.

## What the skill adds

- Adaptive multi-branch reasoning
- Semantic diversity requirements
- Active / dormant / rejected branch states
- Independent verification rules
- Contradiction and shared-assumption checks
- Interference-like cross-branch comparison
- Dynamic compute allocation
- Branch revival
- Explicit stopping / collapse criteria
- Final requirement and contradiction check

## Usage

Install or provide `SKILL.md` to a compatible agent/skill system, then invoke it for difficult reasoning tasks. No Python package or model fine-tuning is required.

See [`examples/usage.md`](./examples/usage.md) for example prompts and expected behavior.

## Status

**v0.2 — skill-first prototype.** The next important step is benchmarking the same models and tasks with and without the skill to measure accuracy, compute cost, branch diversity, and error recovery.
