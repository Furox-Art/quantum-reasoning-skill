# Contributing

Contributions are welcome for the reasoning protocol, reference controller, tests, documentation, benchmark cases, host integrations and independently run model evaluations.

Before changing host-facing behavior, read [`docs/COMPATIBILITY.md`](./docs/COMPATIBILITY.md). Executable behavior changes should include tests.

## Community-run benchmarks

The project does **not** require the maintainer to purchase access to every model or provider. Real model evaluations are intentionally community-run.

The repository provides:

- the benchmark protocol;
- deterministic seed cases;
- machine-readable JSON Schemas;
- the result evaluator;
- a reproducible submission validator;
- CI validation and comparison tooling.

Users may run controlled baseline-vs-skill experiments on models and providers they already have access to and submit the results for review.

### Required metadata

Every submitted model evaluation must identify at least:

- provider;
- exact model and model version when available;
- run date;
- skill version/commit when available;
- baseline and skill prompt/instruction configuration;
- temperature/sampling parameters;
- context and output limits;
- tool availability;
- number of repetitions per case;
- random seed when supported;
- local hardware/runtime details for local models;
- whether failures, refusals and timeouts were retained.

Do not omit failed runs.

### Required artifacts for a benchmark PR

Place each submitted run under:

```text
benchmark/results/community/<provider>-<model>-<YYYY-MM-DD>/
```

Every bundle must include:

```text
metadata.json
cases.jsonl
baseline.jsonl
skill.jsonl
comparison.json
README.md
```

The exact contracts are in [`benchmark/schemas/`](./benchmark/schemas/). `cases.jsonl` must contain the exact evaluated cases, including custom cases when used.

`comparison.json` must be produced by `benchmark/evaluate.py` from the submitted raw result files rather than edited manually. Before submitting, run:

```bash
python benchmark/validate_submission.py --root benchmark/results/community
```

CI recomputes the comparison and rejects a bundle when its raw evidence and reported comparison disagree.

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

For ordinary defects, use the **Bug report** form. For proposed behavior or protocol changes, use the **Feature request** form.

For code or protocol changes, include tests when the change is executable and explain which behavior is being changed. Follow the pull-request checklist in `.github/PULL_REQUEST_TEMPLATE.md`.
