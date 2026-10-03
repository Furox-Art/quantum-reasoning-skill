# Host integration examples

These examples describe integration shapes without depending on a specific provider.
Requirements expressed as capabilities are in [`../docs/COMPATIBILITY.md`](../docs/COMPATIBILITY.md).

**Install from a clone, the PyPI wheel, or npm** — all three ship `SKILL.md`. See
[the distribution section](../README.md#distribution-and-the-surface-it-exposes). After copying `SKILL.md`,
verify the copy with `python docs/quickstart.py`, or against an installed package with
`quantum-reasoning --validate`. `SKILL.md` is the only artifact a host needs to load.

## 1. Native skill directory

If the host supports a skill or plugin directory, install the repository so that
`SKILL.md` is the skill entry point, and keep its YAML front matter intact.

Verify after copying:

```bash
python docs/quickstart.py
```

The script fails if `SKILL.md` is truncated or its front matter is damaged, which is the
usual outcome of a lossy copy.

## 2. Persistent instruction wrapper

If the host has no native skill format, load the contents of `SKILL.md` into the persistent
system or developer instruction layer before the user task:

```text
persistent instructions:
  <contents of SKILL.md>

task:
  <user request>
```

Do not require the model to print private reasoning. The final answer may remain concise
while the host records only observable aggregate telemetry.

Do not prepend `SKILL.md` to benchmark prompts in the skill condition only, unless the
baseline wrapper is otherwise identical. An asymmetric wrapper invalidates the comparison.

## 3. Controller-assisted agent

A host with an explicit agent loop can map observable aggregate branch measurements to
`BranchMetrics` and use [`../reference/branch_controller.py`](../reference/branch_controller.py)
for ranking, state changes and collapse decisions:

```python
from reference.branch_controller import Branch, BranchMetrics, collapse_decision

branch = Branch(
    branch_id="candidate-a",
    metrics=BranchMetrics(
        evidence=0.8,
        verification=0.9,
        independence=0.7,
        information_gain=0.6,
        contradiction=0.1,
        unresolved_assumptions=0.2,
        normalized_cost=0.3,
        shared_assumption_ratio=0.1,
        semantic_similarity_to_leader=0.2,
    ),
)
```

That snippet is taken from [`../docs/quickstart.md`](../docs/quickstart.md) step 3, which
also shows what the controller does with a full branch set — including refusing to
collapse when the leader score is below threshold.

The host supplies only measurements it can actually observe. Missing telemetry must not be
guessed. The weights and thresholds are reference defaults, not validated constants; see
[`../docs/MEASUREMENT.md`](../docs/MEASUREMENT.md).

## 4. Benchmark wrapper

For an A/B benchmark, keep everything fixed except the presence of the skill:

```text
baseline = normal persistent instructions + task
skill    = normal persistent instructions + SKILL.md + same task
```

Use the same model and version, tools, sampling settings and budget policy for both
conditions. Every number you publish from such a run must carry the provenance listed in
[`../CONTRIBUTING.md`](../CONTRIBUTING.md#benchmark-provenance-requirements).

See [`../benchmark/README.md`](../benchmark/README.md) for cases, schemas and the evaluator.