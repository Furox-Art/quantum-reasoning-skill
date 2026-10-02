# Contributing

Contributions are welcome for the reasoning protocol, reference controller, tests,
documentation, benchmark cases, host integrations, and independently run model evaluations.

Read the [Code of Conduct](CODE_OF_CONDUCT.md) before participating.

Before changing host-facing behavior, read [`docs/COMPATIBILITY.md`](docs/COMPATIBILITY.md).
Executable behavior changes should include tests.

## Repository map

| Path | What lives there |
| --- | --- |
| [`SKILL.md`](SKILL.md) | The normative protocol. If a doc and `SKILL.md` disagree, `SKILL.md` wins. |
| [`docs/`](docs/index.md) | Documentation home, getting started, quickstart, measurement, compatibility |
| [`reference/branch_controller.py`](reference/branch_controller.py) | Reference scoring, dormancy, revival and collapse logic |
| [`bin/quantum-reasoning`](bin/quantum-reasoning) | The `quantum-reasoning` console script; installed as `quantum_reasoning_skill.cli` |
| [`bin/check_release_contract.py`](bin/check_release_contract.py) | Release gate: asserts the installed distribution's real surface, with a fail-closed negative control |
| [`conftest.py`](conftest.py) | Version-lockstep helpers shared by CI and the standalone scripts |
| [`examples/`](examples/usage.md) | Prompt shapes and host integration shapes |
| [`benchmark/`](benchmark/README.md) | Cases, JSON Schemas, evaluator, submission validator |
| [`tests/`](tests) | Behavioral tests, run with `python -m unittest discover -s tests` |

## Getting a change merged

1. Open an issue first for anything that changes the protocol, the schemas, or the host
   contract. Use the [feature request](https://github.com/Furox-Art/quantum-reasoning-skill/issues/new?template=feature-request.yml)
   template so the evidence requirement is visible early.
2. Branch from `main`.
3. Run the validation suite. These six checks are the required status checks on `main`:

   ```bash
   python -m unittest discover -s tests -v
   ruff check .
   mypy
   python -m coverage run -m unittest discover -s tests && python -m coverage report
   python -m build --outdir dist && python -m twine check --strict dist/*
   pip install --force-reinstall dist/*.whl && python bin/check_release_contract.py
   ```

   Plus `python docs/quickstart.py` for the user-facing path. `pip install -e .[dev]` or
   the `dev` dependency group in `pyproject.toml` pins the exact tool versions CI uses.

4. Open a pull request and complete [`PULL_REQUEST_TEMPLATE.md`](.github/PULL_REQUEST_TEMPLATE.md).

## Documentation and claim accuracy

This repository makes a specific promise: it does not publish performance claims it cannot
back. Changes must preserve that.

- Every number in a document must be either computed by a script in this repository or
  carried with provenance (see below). Do not paste a result you did not produce.
- Label synthetic, placeholder or illustrative output as such, next to the number.
- Do not describe a distribution channel as an install path unless the published artifact
  actually contains the artifact you claim. `SKILL.md` is the integration surface, and
  `bin/check_release_contract.py` enforces that it ships.
- Do not add a Python API that does not exist. The installed surface is the
  `quantum-reasoning` console script, the shipped `SKILL.md` and `VERSION`, and
  `reference.branch_controller`. An earlier README claimed a `ReasoningSession` class that
  never existed; asserting it made the release gate unsatisfiable.
- Bump `VERSION` and let the lockstep check carry `pyproject.toml`, `package.json`,
  `CITATION.cff` and `CHANGELOG.md` with it. Do not hand-edit one version in isolation.
- Keep `docs/MEASUREMENT.md` in sync with `WEIGHTS` and `DEFAULT_THRESHOLDS` in
  `reference/branch_controller.py`. They are transcribed from each other.
- Link only to files that exist, and prefer relative links inside this repository.

## Community-run benchmarks

The project does **not** require the maintainer to purchase access to every model or
provider. Real model evaluations are intentionally community-run.

The repository provides:

- the benchmark protocol;
- deterministic seed cases;
- machine-readable JSON Schemas;
- the result evaluator;
- a reproducible submission validator;
- CI validation and comparison tooling.

Users may run controlled baseline-vs-skill experiments on models and providers they already
have access to and submit the results for review.

**No such evaluation has been published yet.** `benchmark/cases.jsonl` holds smoke-test
cases that prove the harness runs; they are not evidence that this skill improves reasoning.
Your run would be among the first.

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

### Benchmark provenance requirements

Every reported number must be traceable to a run. State all of the following in the
submission, next to the number:

- the **script** that produced it and its version or commit;
- the **skill version** and git commit under test;
- the **provider** and exact model version;
- the **run date**;
- sampling parameters, context and output limits, tool availability;
- number of repetitions and the seed, when the provider supports one;
- the **platform** and runtime (OS, CPU/GPU, library versions);
- the raw result files required to recompute the number.

A number without these is not submittable. Do not publish a selected percentage or a
hand-picked example in place of the full result set — see
[`docs/MEASUREMENT.md`](docs/MEASUREMENT.md) section 10.

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

The exact contracts are in [`benchmark/schemas/`](benchmark/schemas/). `cases.jsonl` must
contain the exact evaluated cases, including custom cases when used.

`comparison.json` must be produced by `benchmark/evaluate.py` from the submitted raw result
files rather than edited manually. Before submitting, run:

```bash
python benchmark/validate_submission.py --root benchmark/results/community
```

CI recomputes the comparison and rejects a bundle when its raw evidence and reported
comparison disagree.

The bundle `README.md` should carry the provenance block above so a reader can rerun the
evaluation themselves.

### Result integrity

- Use the same model/version, task set, tools, sampling settings and budget policy for
  baseline and skill conditions.
- Do not expose or submit private chain-of-thought.
- Do not fabricate missing telemetry.
- Keep evaluation cases separate from any prompt used while designing or tuning the skill.
- Clearly disclose custom benchmark cases, prompt wrappers, provider-specific adapters and
  any modifications to `SKILL.md`.
- Third-party benchmark submissions are measurements from their submitters, not
  project-maintainer endorsements.
- A single positive run is not sufficient to establish a general performance claim.

### How to submit

You can either:

1. open a **Benchmark result** issue using the
   [repository issue template](https://github.com/Furox-Art/quantum-reasoning-skill/issues/new?template=benchmark-result.yml)
   and link to your artifacts; or
2. open a pull request containing the reproducible result bundle described above.

For ordinary defects, use the
[Bug report](https://github.com/Furox-Art/quantum-reasoning-skill/issues/new?template=bug-report.yml)
form. For usage or documentation questions, use the
[Question](https://github.com/Furox-Art/quantum-reasoning-skill/issues/new?template=question.yml)
form. For proposed behavior or protocol changes, use the
[Feature request](https://github.com/Furox-Art/quantum-reasoning-skill/issues/new?template=feature-request.yml)
form.

For code or protocol changes, include tests when the change is executable and explain which
behavior is being changed. Follow the pull-request checklist in
`.github/PULL_REQUEST_TEMPLATE.md`.

## Reporting security issues

Not through a public issue. Follow [`SECURITY.md`](SECURITY.md).