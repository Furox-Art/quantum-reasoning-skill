# Quantum Reasoning Skill

[![PyPI](https://img.shields.io/pypi/v/quantum-reasoning-skill)](https://pypi.org/project/quantum-reasoning-skill/)
[![npm](https://img.shields.io/npm/v/quantum-reasoning-skill)](https://www.npmjs.com/package/quantum-reasoning-skill)
[![PyPI stats](https://img.shields.io/badge/PyPI%20stats-informational)](https://pypi.org/project/quantum-reasoning-skill/#stats)
[![License](https://img.shields.io/badge/license-MIT-blue)](LICENSE)

A model-facing [Agent Skill](SKILL.md) that keeps several genuinely different hypotheses
alive, tests each one against evidence and tools, revives alternatives when new evidence
arrives, and collapses to the best-supported answer only at the end.

> **Status: protocol implemented, effectiveness not yet demonstrated.**
> The skill contract, the reference branch controller and the benchmark harness are in
> this repository and run. **No baseline-vs-skill model evaluation has been published,**
> so this project makes **no claim that it improves accuracy or costs less compute.**
> Read [Benchmark status](#benchmark-status) before citing any number from this repository.

## Why

Most assistant answers follow one path and then justify it:

1. Here's a plausible answer
2. Let me justify it
3. Done

Real thinking explores multiple paths, tests them against evidence, and commits only when
the alternatives have been genuinely eliminated. This skill makes that process explicit
and auditable instead of implicit.

It is a **metaphor, not quantum computing.** It runs on ordinary models and ordinary
hardware. Nothing here uses quantum primitives; "superposition" means "keep more than
one candidate open", and "measurement" means "let evidence collapse it".

## Quick start

`SKILL.md` is the deliverable. Three verified paths reach it:

```bash
# Option 1 — from a clone (nothing to install)
git clone https://github.com/Furox-Art/quantum-reasoning-skill.git
cd quantum-reasoning-skill
python docs/quickstart.py

# Option 2 — from the wheel; `SKILL.md` ships inside the distribution
pip install quantum-reasoning-skill
quantum-reasoning --validate

# Option 3 — from npm
npm i quantum-reasoning-skill
npx quantum-reasoning --validate
```

Then copy `SKILL.md` into your host's skill directory, preserving the YAML front matter.
`docs/getting-started.md` covers the integration shapes, and
`examples/host-integration.md` shows the persistent-instruction wrapper.

`docs/quickstart.py` verifies the checkout, exercises the reference branch controller, and
smoke-tests the benchmark harness. It calls no language model and invents no metrics.

<details>
<summary>Verified <code>docs/quickstart.py</code> output</summary>

Captured by running `python docs/quickstart.py` on Windows 11 / CPython 3.12.10 at
commit `727baf8fe7452532bc014bc864931fc5b9f1b4ca`, the commit that introduced the
script. The `commit`, `branch` and `SKILL.md` digest lines change with your checkout;
every other line is deterministic for a given commit.

```text
Quantum Reasoning Skill - quickstart verification
--------------------------------------------------------------

[1/4] Checkout identity
    commit      : 727baf8fe7452532bc014bc864931fc5b9f1b4ca
    VERSION     : 0.3.1
    SKILL.md    : 7291 bytes  sha256:a63dd27330017a3c
    branch      : docs/honest-discoverability

[2/4] Agent Skill contract (SKILL.md)
    name        : quantum-reasoning
    description : 266 chars
    body        : 142 lines
    status      : front matter parses and is host-ready

[3/4] Reference controller (reference/branch_controller.py)
    scenario: 'should we migrate our monolith to microservices?'
      strangler-fig-incremental  active
      big-bang-rewrite           rejected
      modular-monolith           active
      feature-flag-carveout      dormant
    uncertainty : 0.9651
    next width  : 6-10 branches (high uncertainty -> widen)
    leader      : strangler-fig-incremental
    collapse    : BLOCKED - leader score below collapse threshold
    revival     : feature-flag-carveout -> active (evidence +0.25 >= 0.15)
    surviving   : 3 branches

[4/4] Benchmark evaluator smoke run - SYNTHETIC PLACEHOLDER ROWS
    No language model is called. Baseline and skill rows below are
    byte-identical placeholders that exist only to prove the harness runs.
    The resulting accuracy is NOT a measurement of this skill.
    cases       : 6 seed cases
    accuracy    : 0.1667 (both conditions)
    delta       : +0.0000 accuracy, +0.0% tokens
    reading     : 0.00 delta is the expected result for identical
                 placeholder rows. It is a harness check, not evidence.

--------------------------------------------------------------
Provenance for every number printed above
--------------------------------------------------------------
    script      : docs/quickstart.py
    skill ver   : 0.3.1   (VERSION)
    commit      : 727baf8fe7452532bc014bc864931fc5b9f1b4ca
    platform    : Windows 11 (AMD64)
    python      : 3.12.10 (CPython)
    controller  : reference/branch_controller.py DEFAULT_THRESHOLDS
    benchmark   : benchmark/cases.jsonl + benchmark/evaluate.py

RESULT: PASS (structure verified; no performance claim implied)
```

Note step 3: the reference thresholds **refuse to collapse** in that scenario because the
leader's score is below the collapse threshold. That refusal is the intended behaviour, and
it is the clearest illustration that these numbers are uncalibrated defaults rather than
tuned constants.

</details>

## Distribution status

All three channels ship `SKILL.md` and are verified by CI against the **built**
distribution, not against a checkout.

| Channel | Ships | Verified by |
| --- | --- | --- |
| `git clone` | `SKILL.md`, `VERSION`, `reference/`, `benchmark/`, `docs/`, `examples/`, `bin/` | — |
| `pip install quantum-reasoning-skill` | `SKILL.md` and `VERSION` inside the package as `quantum_reasoning_skill/SKILL.md` and `.../VERSION`; the `reference/`, `benchmark/`, `docs/` and `examples/` trees; plus the `quantum-reasoning` console script | installed API contract gate |
| `npm i quantum-reasoning-skill` | `SKILL.md`, `VERSION`, `index.js`, `LICENSE`, `README.md` and the `quantum-reasoning` bin | `npm pack` + `npx` smoke test |

Locate the installed asset and check the contract:

```bash
quantum-reasoning --validate   # Python: exits non-zero on an invalid contract
npx quantum-reasoning --validate  # npm: same report
```

`bin/check_release_contract.py` is the gate CI runs. It asserts that `SKILL.md` resolves
inside the installed wheel, that the `quantum-reasoning` console entry point is installed
and returns success against the installed asset, that `reference.branch_controller` imports
from the installed distribution with a callable API, and that the release version agrees
across `VERSION`, `pyproject.toml`, `package.json` and `CITATION.cff`. A negative-control
mode removes each installed asset and requires the gate to fail, so the gate cannot degrade
into a no-op.

Version numbers are locked: one release version across `VERSION`, `pyproject.toml`,
`package.json`, `CITATION.cff` and `CHANGELOG.md`, enforced in CI and in both release
workflows. Read the authoritative value from the `VERSION` file rather than from a badge.

### What the Python distribution actually exposes

There is **no `ReasoningSession` class** — an earlier README claimed one, it never existed,
and the claim has been removed. The installed surface is exactly this:

| Surface | What it is |
| --- | --- |
| `quantum-reasoning` console script | Reads the installed `SKILL.md` and reports the skill contract. `--validate` exits non-zero on an invalid contract, `--json` emits the report, `--path` prints the asset location |
| `quantum_reasoning_skill.SKILL.md`, `quantum_reasoning_skill.VERSION` | The shipped skill contract and version, installed as package data |
| `reference.branch_controller` | The reference scoring, dormancy, revival and collapse functions documented in [Measurement methodology](docs/MEASUREMENT.md) |
| `quantum_reasoning_skill` | Namespace for the shipped asset; it deliberately exposes no Python class API |

The gate that enforces this list is [`bin/check_release_contract.py`](bin/check_release_contract.py),
and it runs on every pull request. If a release ever shipped a wheel that installed but
carried no skill, that gate fails the release.

## The protocol

1. **Frame the problem** — what is verified versus assumed?
2. **Open branches** — genuinely different approaches, not paraphrases
3. **Evaluate independently** — each branch judged on evidence, not eloquence
4. **Cross-check** — conclusions reached independently by separate paths get reinforced
5. **Prune and revive** — kill contradicted paths, keep dormant ones recoverable
6. **Collapse** — only when one path is clearly better supported than the rest

`SKILL.md` is the normative contract. The weights and thresholds in
[`reference/branch_controller.py`](reference/branch_controller.py) are
**reference defaults, not validated constants**; see
[`docs/MEASUREMENT.md`](docs/MEASUREMENT.md) for the formulas and the list of values that
must be calibrated before they mean anything.

## Benchmark status

**There are no published benchmark results.** `benchmark/README.md` describes the
protocol, `benchmark/cases.jsonl` holds six deterministic smoke-test cases, and
`benchmark/evaluate.py` computes baseline-versus-skill deltas. Those seed cases are
explicitly **not sufficient evidence of reasoning improvement** — they exist to prove the
harness runs.

Anyone can run the evaluation on models they already have access to. The required metadata
and integrity rules are in [`CONTRIBUTING.md`](CONTRIBUTING.md), and every submitted number
must carry provenance: script path and version, skill commit, provider and exact model
version, run date, sampling parameters, repetition count, and platform. A single positive
run is not sufficient to establish a general performance claim.

## How it compares

This table describes *mechanisms*, not measured performance. Nothing here has been
benchmarked against the rows above it.

| Approach | Mechanism | Limitation |
| --- | --- | --- |
| Chain-of-Thought ([Wei et al., 2022](https://arxiv.org/abs/2201.11903)) | One linear reasoning path | Early anchoring; alternatives are never kept alive |
| Tree-of-Thought ([Yao et al., 2023](https://arxiv.org/abs/2305.10601)) | Branch plus heuristic scoring | Scoring is fixed in advance; no evidence weighting or revival |
| Self-consistency ([Wang et al., 2022](https://arxiv.org/abs/2203.11171)) | Samples one prompt N times | Paraphrase diversity, not hypothesis diversity |
| **This skill** | Branches with explicit evidence-weighted scores, correlation penalties, dormancy with revival, and explicit collapse criteria | **Not yet validated:** no published baseline-vs-skill result. Branch breadth costs tokens and latency. Requires a host that can persist instructions; it is not a drop-in model call. |

## When to use it

Use it for problems that are difficult, ambiguous, multi-step, or vulnerable to early
commitment: mathematics, scientific reasoning, debugging, planning, architecture, model
selection, hypothesis testing, technical diagnosis.

Do not add branching overhead to trivial questions.

## Documentation

- [Documentation home](docs/index.md)
- [Getting started](docs/getting-started.md) — install and first use
- [Quickstart and verified output](docs/quickstart.md) — runnable check with provenance
- [Skill contract](SKILL.md) — normative protocol
- [Usage examples](examples/usage.md)
- [Host integration](examples/host-integration.md)
- [Branch controller reference](reference/branch_controller.py)
- [Measurement methodology](docs/MEASUREMENT.md)
- [Compatibility notes](docs/COMPATIBILITY.md)
- [Benchmark documentation](benchmark/README.md)
- [Contributing](CONTRIBUTING.md) — including benchmark submission rules
- [Code of conduct](CODE_OF_CONDUCT.md)
- [Security policy](SECURITY.md)
- [Changelog](CHANGELOG.md)
- [Citation metadata](CITATION.cff)
- [Version file](VERSION)

## License

[MIT](LICENSE)