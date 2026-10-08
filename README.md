# Quantum Reasoning Skill

[![PyPI](https://img.shields.io/pypi/v/quantum-reasoning-skill)](https://pypi.org/project/quantum-reasoning-skill/)
[![npm](https://img.shields.io/npm/v/quantum-reasoning-skill)](https://www.npmjs.com/package/quantum-reasoning-skill)
[![PyPI stats](https://img.shields.io/badge/PyPI%20stats-informational)](https://pypi.org/project/quantum-reasoning-skill/#stats)
[![License](https://img.shields.io/badge/license-MIT-blue)](LICENSE)

A model-facing [Agent Skill](SKILL.md) that keeps several genuinely different hypotheses
alive, tests each against evidence and tools, revives alternatives when new evidence arrives,
and collapses to the best-supported answer only at the end. It is a **metaphor, not quantum
computing** — "measurement" means letting evidence collapse a branch.

> **Status: protocol implemented, controller benchmark published, model evaluation pending.**
> The skill contract, the reference controller, the benchmark harness and a deterministic
> falsification benchmark are here and run. **A baseline-vs-skill model evaluation has NOT
> been published**, so this project makes **no claim that it improves any language model's
> accuracy.** See [Benchmark status](#benchmark-status) before citing any number from here.

## Quick start

`SKILL.md` is the deliverable. Three verified paths reach it:

```bash
# 1. from a clone — nothing to install
git clone https://github.com/Furox-Art/quantum-reasoning-skill.git
cd quantum-reasoning-skill
python docs/quickstart.py

# 2. from PyPI — SKILL.md ships inside the wheel
pip install quantum-reasoning-skill
quantum-reasoning --validate

# 3. from npm — also published
npm i quantum-reasoning-skill
npx quantum-reasoning --validate
```

Copy `SKILL.md` into your host's skill directory, keeping the YAML front matter.
[`docs/getting-started.md`](docs/getting-started.md) walks the install; prompt shapes are in
[`examples/usage.md`](examples/usage.md), host integration shapes in
[`examples/host-integration.md`](examples/host-integration.md), and required host
capabilities in [`docs/COMPATIBILITY.md`](docs/COMPATIBILITY.md).

`docs/quickstart.py` verifies the checkout, parses the front matter, exercises the controller
and smoke-tests the benchmark harness; it calls no model and invents no metrics. **Its
verified output is in [`docs/quickstart.md`](docs/quickstart.md)**, which is the single source
for it — including the scenario where the thresholds *refuse* to collapse, the clearest
evidence they are uncalibrated defaults. It is not duplicated here, because a pasted copy
drifts.

## Distribution and the surface it exposes

Three channels ship `SKILL.md`, all on one version: a `git clone` (everything); the PyPI
wheel (`SKILL.md` + `VERSION` as package data, plus `reference/`, `benchmark/`, `docs/`,
`examples/`, and a `quantum-reasoning` console script); and the npm tarball (`SKILL.md`,
`VERSION`, `index.js`, `LICENSE`, `README.md`, and a `quantum-reasoning` bin). Both packaged
artifacts are verified against the **built** artifact, not a checkout.

### Supply-chain attestations

Only some published versions carry a build attestation, so check before relying on one:

| release | npm attestation | PyPI PEP 740 attestation |
| --- | --- | --- |
| `1.1.0` (npm) | yes — SLSA provenance and npm publish attestation, Sigstore | n/a |
| `1.1.1` (npm and PyPI) | **no** | **no** |

`1.1.1` was published through the long-lived-token path, which cannot produce a Sigstore
attestation. Attestations are bound to a publish event and cannot be added afterwards, so
this is permanent for that version. The package itself is unchanged and passes the same
release contract as every other version; only the provenance *record* is missing.

If you need to verify how a build was produced, use `1.1.0` on npm. To check an attestation
yourself:

```bash
curl -sS -o /dev/null -w '%{http_code}\n' \
  https://registry.npmjs.org/-/npm/v1/attestations/quantum-reasoning-skill@1.1.0   # 200
curl -sS -o /dev/null -w '%{http_code}\n' \
  https://registry.npmjs.org/-/npm/v1/attestations/quantum-reasoning-skill@1.1.1   # 404
```

A missing attestation is not evidence of tampering. Versions are locked
across `VERSION`, `pyproject.toml`, `package.json`, `CITATION.cff` and `CHANGELOG.md` — read
the value from `VERSION`, not a badge ([details](CONTRIBUTING.md#toolchain-pinning)).

There is **no `ReasoningSession` class**. An earlier README claimed one, it never existed, and
asserting it made the release gate unsatisfiable. The real surface is two *non-compatible*
CLIs plus a library:

| Surface | Flags it actually accepts |
| --- | --- |
| `quantum-reasoning` — **Python** console script ([`bin/quantum-reasoning`](bin/quantum-reasoning)) | `--skill-file PATH`, `--validate`, `--json`, `--quiet`, `--help` |
| `npx quantum-reasoning` — **npm** CLI ([`index.js`](index.js)) | `--validate`, `--json`, `--path`, `--help` |
| `reference.branch_controller` — Python library | importable; see [Reference controller](#reference-controller) |
| `quantum_reasoning_skill.SKILL.md`, `.VERSION` | the shipped asset, as package data |

`--path` is npm-only; `--skill-file` and `--quiet` are Python-only. An unsupported flag exits
`2`.

## Release contract

[`bin/check_release_contract.py`](bin/check_release_contract.py) is the gate CI runs before
any release. It asserts that `SKILL.md` resolves inside the installed wheel, that the
`quantum-reasoning` entry point is installed and succeeds against the installed asset, that
`reference.branch_controller` imports with a callable API, and that the version agrees
everywhere.

**Twelve public names in `reference/branch_controller.py` are frozen** — `DEFAULT_THRESHOLDS`,
`Branch`, `BranchMetrics`, `BranchState`, `Thresholds`, `branch_score`, `classify_branch`,
`collapse_decision`, `diversity_ratio`, `recommended_width`, `uncertainty_from_branches`,
`update_branch_state`. Renaming or removing any one **halts the release**. `WEIGHTS` is
deliberately *not* on the list: the scoring model can change without breaking the contract.

A **negative-control mode** proves the gate is fail-closed across four scenarios — removing
the installed `SKILL.md`, emptying it, and feeding the controller check a stub missing its
public API and a module returning wrong values — requiring each to be rejected. It does **not**
exercise `VERSION` or the console entry point.

## Reference controller

The control loop behind the protocol: it scores branches, moves them between `active` /
`dormant` / `rejected`, revives recoverable ones, and decides when a search may collapse. It
never generates reasoning and never calls a model — it only consumes measurements you supply.

| Function | Role |
| --- | --- |
| `WEIGHTS`, `DEFAULT_THRESHOLDS`, `Thresholds` | the scoring model: per-metric weights, and the state / revival / collapse thresholds |
| `BranchMetrics`, `Branch`, `BranchState` | input types; `BranchMetrics` rejects values outside `[0, 1]` |
| `branch_score`, `effective_independence` | weighted score in `[0, 1]`, after penalising branches that share assumptions or near-duplicate a leader |
| `classify_branch`, `update_branch_state`, `should_revive` | move a branch to `dormant` or `rejected`, or revive it on material new evidence |
| `collapse_decision` | `(can_collapse, reason, leader)`; refuses when the margin is too small or a strong alternative is unresolved |
| `uncertainty_from_branches`, `normalized_entropy` | normalised Shannon entropy over surviving branch scores |
| `recommended_width` | uncertainty → suggested branch count for the next step |
| `diversity_ratio`, `rank_branches` | fraction of branch pairs that are materially distinct; ordering helper |

Weights and thresholds are **reference defaults, not validated constants** —
[`docs/MEASUREMENT.md`](docs/MEASUREMENT.md) gives the formulas and the list of values that
must be calibrated first.

## Benchmark harness

[`benchmark/`](benchmark/README.md) measures whether the skill helps rather than merely
producing more text: `benchmark/evaluate.py` (evaluator), `benchmark/validate_submission.py`
(machine-validates a reproducible bundle), `benchmark/paths.py` (path confinement that rejects
`..` traversal and symlink escapes), `benchmark/cases.jsonl`, and four JSON Schemas — `case`,
`result`, `metadata`, `comparison`.

```bash
python benchmark/evaluate.py --cases benchmark/cases.jsonl --skill skill-results.jsonl
```

Inputs are confined to `--cases-dir` (default: each input's own directory), `--output` must
stay inside it, and reads are bounded by `--max-bytes`. Both `python benchmark/evaluate.py`
and `python -m benchmark.evaluate` work.

## Tests, tooling and governance

About **43% of the Python here is tests** — 1,575 of 3,635 lines across **9 test modules**,
run with the standard library's `unittest` on Python 3.10–3.14 on Linux, Windows and macOS.
They cover the controller, the benchmark harness, import hardening, path boundaries,
dependency-lock drift and release-gate polling; `tests/test_readme_badges.py` keeps this
file's badges honest. The toolchain is pinned twice — `pyproject.toml`'s `dev` group with
`==`, and [`constraints.txt`](constraints.txt) with `==` **and** `--hash` digests for the full
transitive closure ([details](CONTRIBUTING.md#toolchain-pinning)).

Also here: [`codemeta.json`](codemeta.json) for machine-readable citation beside
[`CITATION.cff`](CITATION.cff); five issue templates (bug, feature, question, benchmark
result, plus a chooser in `config.yml`) and a pull-request template; a
[Code of Conduct](CODE_OF_CONDUCT.md) with a scientific-integrity section; a
[Security policy](SECURITY.md).

## The protocol

`SKILL.md` is the normative contract. In short: **frame** the problem (verified vs assumed) →
**open branches** (genuinely different, not paraphrases) → **evaluate independently** (on
evidence, not eloquence) → **cross-check** (independently reached conclusions get reinforced)
→ **prune and revive** (kill contradicted paths, keep dormant ones recoverable) → **collapse**
(only when one path is clearly better supported). `SKILL.md` also scopes when *not* to use it:
trivially answerable questions should not pay branching cost.

## Benchmark status

**What has been measured — the controller, not the model.** On 9 deterministic falsification
scenarios, the multi-hypothesis branch controller achieved **100% final accuracy versus 22%**
for a single-hypothesis policy that commits to its first leader (0/4 on falsification
scenarios, 0/3 on revival scenarios; both policies scored 2/2 on the control scenarios). It
abandoned the falsified hypothesis at the same evidence step the falsification arrived, and
revived a rejected-then-supported alternative in 3/3 revival scenarios. Confidence calibration
showed **no difference** (Brier score 0.033 vs 0.033), and the accuracy gain cost **109.6%
more tokens** per scenario. Methodology and reproduction:
[`benchmark/falsification/METHODOLOGY.md`](benchmark/falsification/METHODOLOGY.md).

These results measure the reference decision controller on **synthetic evidence streams**, not
any language model. `benchmark/cases.jsonl` holds six deterministic smoke-test cases that
prove the harness runs; they are explicitly **not sufficient evidence of reasoning
improvement**. A baseline-vs-skill **model** evaluation has not been published, so this
project makes **no claim that it improves any language model's accuracy or costs less
compute.** Anyone can evaluate on models they have access to; every submitted
number must carry provenance (script, skill commit, provider and exact model version, run date,
sampling parameters, repetitions, platform), and one positive run establishes no general claim.
Rules: [CONTRIBUTING.md](CONTRIBUTING.md#benchmark-provenance-requirements).

## How it compares

This table describes *mechanisms*, not measured performance. Nothing here has been
benchmarked against the rows above it.

| Approach | Mechanism | Limitation |
| --- | --- | --- |
| Chain-of-Thought ([Wei et al., 2022](https://arxiv.org/abs/2201.11903)) | One linear reasoning path | Early anchoring; alternatives are never kept alive |
| Tree-of-Thought ([Yao et al., 2023](https://arxiv.org/abs/2305.10601)) | Branch plus heuristic scoring | Scoring is fixed in advance; no evidence weighting or revival |
| Self-consistency ([Wang et al., 2022](https://arxiv.org/abs/2203.11171)) | Samples one prompt N times | Paraphrase diversity, not hypothesis diversity |
| **This skill** | Branches with evidence-weighted scores, correlation penalties, dormancy with revival, explicit collapse criteria | **Not yet validated:** no published result. Branch breadth costs tokens and latency. Needs a host that persists instructions. |

## Documentation

Everything lives in [`docs/index.md`](docs/index.md) — getting started, quickstart and its
verified output, measurement methodology, host compatibility, report forms. Release history:
[CHANGELOG.md](CHANGELOG.md). License: [MIT](LICENSE).
