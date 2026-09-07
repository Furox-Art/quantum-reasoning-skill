# Benchmark protocol

This directory measures whether the skill improves results rather than merely producing more reasoning text.

## Principle

Run the **same model, model version, task set, tool access, temperature/sampling settings, and token budget policy** twice:

1. baseline: normal instructions without `SKILL.md`
2. skill: the same setup with `SKILL.md`

Do not compare different models and attribute the difference to the skill.

## Seed cases

`cases.jsonl` contains deterministic smoke-test cases. They are intentionally small and are **not sufficient evidence of reasoning improvement**. A serious evaluation should add difficult held-out tasks from the target domains and report their provenance/licensing.

Each case has:

```json
{"id":"...","domain":"...","prompt":"...","accepted_answers":["..."]}
```

## Result schema

A runner should write one JSON object per case. Required fields:

```json
{
  "case_id": "math-arithmetic-001",
  "answer": "323",
  "tokens": 120,
  "tool_calls": 0,
  "latency_ms": 950
}
```

Skill-aware runners should additionally record, when observable without exposing hidden chain-of-thought:

```json
{
  "branches_total": 5,
  "branches_distinct": 4,
  "revived_branches": 1,
  "recovered_errors": 1,
  "contradictions_found": 2,
  "contradictions_resolved": 2
}
```

These are aggregate control-plane measurements. Do not store private chain-of-thought.

## Evaluate one run

```bash
python benchmark/evaluate.py \
  --cases benchmark/cases.jsonl \
  --skill path/to/skill-results.jsonl
```

## Compare baseline vs skill

```bash
python benchmark/evaluate.py \
  --cases benchmark/cases.jsonl \
  --baseline path/to/baseline-results.jsonl \
  --skill path/to/skill-results.jsonl \
  --output benchmark/results/comparison.json
```

The evaluator reports:

- exact-answer accuracy
- mean token use
- mean tool calls
- mean latency
- branch diversity ratio
- branch revival count per case
- recovered-error count per case
- contradiction resolution rate
- baseline-to-skill deltas

## Required experimental controls

For a publishable comparison, record at minimum:

- provider and exact model/version
- date of the run
- decoding/sampling parameters
- context and output limits
- tool availability
- prompt wrapper/system instructions
- number of repetitions per case
- random seed when the provider supports one
- hardware/runtime details for local models
- failures, refusals and timeouts rather than silently dropping them

Use multiple repetitions for stochastic models and report confidence intervals. Keep benchmark cases separate from any prompts used while designing or tuning the skill.

## Interpretation

A useful result is not simply "skill accuracy is higher". Report the trade-off between accuracy and compute. A skill that gains 1 percentage point while using 5x tokens may be undesirable for many workloads.

The reference thresholds in `reference/branch_controller.py` are defaults to test, not validated constants. Benchmark evidence should drive later calibration.
