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
  -> score / classify branches
  -> allocate compute dynamically
  -> suspend or reject weak branches
  -> revive branches when evidence changes
  -> verify collapse criteria
  -> select the best-supported answer
```

## Design goals

- Reduce early lock-in to the first plausible answer.
- Maintain genuinely independent hypotheses or solution strategies.
- Prefer falsification and tool-based verification over self-confidence.
- Expand search when uncertainty is high and concentrate compute when evidence is strong.
- Detect correlated branches so repeated assumptions are not counted as independent evidence.
- Keep high-information alternatives recoverable instead of deleting them too early.
- Work across models and providers that support instruction-following skills.
- Make reasoning-control decisions measurable without exposing private chain-of-thought.

## What the repository now contains

- [`SKILL.md`](./SKILL.md) — model-facing protocol
- [`reference/branch_controller.py`](./reference/branch_controller.py) — deterministic reference scoring, state transition, revival, uncertainty and collapse logic
- [`docs/MEASUREMENT.md`](./docs/MEASUREMENT.md) — explicit formulas, thresholds and calibration requirements
- [`benchmark/cases.jsonl`](./benchmark/cases.jsonl) — deterministic seed cases
- [`benchmark/evaluate.py`](./benchmark/evaluate.py) — baseline-vs-skill evaluator for accuracy, cost, latency and control telemetry
- [`benchmark/README.md`](./benchmark/README.md) — reproducible benchmark protocol and result schema
- [`tests/`](./tests/) — behavioral tests for the controller and evaluator
- GitHub Actions validation on pushes and pull requests

## Core capabilities

- Adaptive multi-branch reasoning
- Semantic diversity requirements
- Active / dormant / rejected branch states
- Independent verification rules
- Contradiction and shared-assumption checks
- Correlation penalty for duplicated/shared-assumption branches
- Interference-like cross-branch comparison
- Dynamic compute allocation from uncertainty
- Measurable branch revival rules
- Explicit stopping / collapse criteria
- Baseline-vs-skill benchmark telemetry
- Final requirement and contradiction check

## Usage

Install or provide `SKILL.md` to a compatible agent/skill system, then invoke it for difficult reasoning tasks. No Python package or model fine-tuning is required to use the skill itself.

See [`examples/usage.md`](./examples/usage.md) for prompt examples.

The Python reference implementation is optional. It exists to make the qualitative policy auditable and testable:

```python
from reference.branch_controller import Branch, BranchMetrics, collapse_decision
```

## Benchmarking

Do not treat the repository's reference thresholds as proof that the skill improves a model. The intended test is a controlled A/B comparison using the **same model, task set, tools and decoding configuration** with and without `SKILL.md`.

```bash
python benchmark/evaluate.py \
  --cases benchmark/cases.jsonl \
  --baseline path/to/baseline-results.jsonl \
  --skill path/to/skill-results.jsonl \
  --output benchmark/results/comparison.json
```

The evaluator measures exact-answer accuracy, token use, tool calls, latency, branch diversity, revival/error recovery and contradiction resolution when those telemetry fields are available.

See [`benchmark/README.md`](./benchmark/README.md) for the complete protocol.

## Validation

Run the repository checks locally with:

```bash
python -m unittest discover -s tests -v
python benchmark/evaluate.py --help
```

CI also validates the skill contract, links, Python syntax, benchmark seed data and unit tests.

## Status

**v0.3 development — measurable prototype.** The branch-control mechanism and benchmark infrastructure now exist, but no empirical performance improvement is claimed until controlled model runs are collected and published.
