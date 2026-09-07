# Contributing

Contributions are welcome for the reasoning protocol, reference controller, tests, documentation, benchmark cases and independently run model evaluations.

## Community-run benchmarks

The project does **not** require the maintainer to purchase access to every model or provider. Real model evaluations are intentionally community-run.

The repository provides:

- the benchmark protocol;
- deterministic seed cases;
- the result schema;
- the evaluator;
- validation and comparison tooling.

Users may run controlled baseline-vs-skill experiments on models and providers they already have access to and submit the results for review.

### Required metadata

Every submitted model evaluation must identify at least:

- provider;
- exact model and model version when available;
- run date;
- baseline and skill prompt/instruction configuration;
- temperature/sampling parameters;
- context and output limits;
- tool availability;
- number of repetitions per case;
- random seed when supported;
- local hardware/runtime details for local models;
- failures, refusals and timeouts.

Do not omit failed runs.

### Required artifacts for a benchmark PR

Place a submitted run under:

```text
benchmark/results/community/<provider>-<model>-<YYYY-MM-DD>/
```

Include, where applicable:

```text
metadata.json
baseline.jsonl
skill.jsonl
comparison.json
README.md
```

`comparison.json` should be produced by `benchmark/evaluate.py` from the submitted raw result files rather than edited manually.

### Result integrity

- Use the same model/version, task set, tools, sampling settings and budget policy for baseline and skill conditions.
- Do not expose or submit private chain-of-thought.
- Do not fabricate missing telemetry.
- Clearly disclose custom benchmark cases, prompt wrappers, provider-specific adapters and any modifications to `SKILL.md`.
- Third-party benchmark submissions are measurements from their submitters, not project-maintainer endorsements.
- A single positive run is not sufficient to establish a general performance claim.

### How to submit

You can either:

1. open a **Benchmark result** issue using the repository issue template and link to your artifacts; or
2. open a pull request containing the reproducible result bundle described above.

For code or protocol changes, include tests when the change is executable and explain which behavior is being changed.
