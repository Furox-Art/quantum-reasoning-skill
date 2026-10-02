# Usage examples

Prompt shapes for hosts that load [`../SKILL.md`](../SKILL.md) as a persistent skill
instruction. Install it first: [Getting started](../docs/getting-started.md).

Use these only when branching is worth the extra tokens and latency. They are prompt
templates, not measured configurations.

## Scientific hypothesis

```text
Use the quantum-reasoning skill. Keep several materially different mechanisms alive, identify what evidence would falsify each one, use available tools to test them, and collapse only after cross-comparison.
```

## Mathematics

```text
Use the quantum-reasoning skill. Explore independent solution strategies, test edge cases and counterexamples, verify the strongest path, and return only the final derivation and important uncertainty.
```

## Debugging

```text
Use the quantum-reasoning skill. Maintain multiple root-cause hypotheses, design the cheapest discriminating test for each, eliminate contradicted causes, revive alternatives if new evidence conflicts with the leader, then give the most supported diagnosis.
```

## Planning / architecture

```text
Use the quantum-reasoning skill. Generate genuinely different architectures, compare assumptions and failure modes, allocate more analysis to unresolved high-impact choices, and synthesize the strongest design only after verification.
```

## Branch selection under cost pressure

```text
Use the quantum-reasoning skill. Open candidate approaches, but report the token and tool
cost of each alongside its support score. If no branch is clearly better than the runner-up,
return the two strongest options and the single cheapest test that would separate them.
```

## Expected behavior

The model should not print a large internal reasoning tree. It should use the branching
protocol internally and return a concise result: the conclusion, the evidence that matters,
the remaining uncertainty, and genuinely unresolved alternatives when necessary.

Host-side aggregate telemetry may be recorded without exposing private reasoning. If the
host cannot observe a measurement, it must omit that measurement rather than invent one.

## What these examples do not tell you

Whether any of the above improves accuracy for your model and workload. That requires an
A/B run on your own setup, following
[`../benchmark/README.md`](../benchmark/README.md) and the provenance rules in
[`../CONTRIBUTING.md`](../CONTRIBUTING.md#benchmark-provenance-requirements).