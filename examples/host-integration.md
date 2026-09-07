# Host integration examples

These examples describe integration shapes without depending on a specific provider.

## Native skill host

Install the repository or copy `SKILL.md` into the host's skill directory. Preserve the YAML front matter and load the file as a persistent skill instruction.

## Persistent instruction host

Conceptually, the host should build the request as:

```text
persistent instructions:
  <contents of SKILL.md>

task:
  <user request>
```

Do not require the model to print private reasoning. The final answer may remain concise while the host records only observable aggregate telemetry.

## Controller-assisted host

A host-side agent loop may use the optional reference controller:

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

The host supplies only measurements it can actually observe. Missing telemetry must not be guessed.

## Benchmark wrapper

For an A/B benchmark, keep everything fixed except the presence of the skill:

```text
baseline = normal persistent instructions + task
skill    = normal persistent instructions + SKILL.md + same task
```

Use the same model/version, tools, sampling settings and budget policy for both conditions. See [`../benchmark/README.md`](../benchmark/README.md).
