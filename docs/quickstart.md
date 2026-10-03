# Quickstart

A runnable check that your checkout is intact and that the shipped tooling actually
executes. It is the fastest way to decide whether this repository is useful to you.

## Run it

```bash
git clone https://github.com/Furox-Art/quantum-reasoning-skill.git
cd quantum-reasoning-skill
python docs/quickstart.py
```

Requirements: Python 3.10 or newer. No third-party dependencies, no network access, no
language-model calls. Exit code `0` means every structural check passed.

## What each step proves — and what it does not

| Step | Proves | Does **not** prove |
| --- | --- | --- |
| 1. Checkout identity | The clone is complete and reports a commit, version and `SKILL.md` digest | Anything about skill quality |
| 2. Agent Skill contract | `SKILL.md` opens with parseable YAML front matter, declares `name: quantum-reasoning`, and has a description inside the 1024-character host limit | That any host has loaded it |
| 3. Reference controller | Scoring, rejection, dormancy, uncertainty-driven width, collapse gating and revival all execute on real inputs | That the weights or thresholds are correct — they are uncalibrated defaults |
| 4. Benchmark harness | `benchmark/evaluate.py` reads the seed cases and emits a comparison document | That the skill helps. The rows are **synthetic placeholders** |

Step 4 writes byte-identical placeholder rows into both the baseline and the skill
condition. A `+0.0000` accuracy delta is therefore the *expected* output. It is a harness
check, not a measurement.

## Verified output

Captured on Windows 11 / AMD64, CPython 3.12.10, on an **LF checkout** (no
`core.autocrlf` translation) at commit
`9a78b15485c47f78a6274ec4e60470bc150532fd`, whose parent is `main`
(`dc0a5930aa0098238adb3a0ab0e2fca01e30b1d4`), so the commit is obtainable by anyone
reading this repository.

**Provenance for the block below:**

- Script: `docs/quickstart.py`
- Skill version: `1.1.0` (from `VERSION`)
- Skill commit: `9a78b15485c47f78a6274ec4e60470bc150532fd`
- Controller: `reference/branch_controller.py`, `DEFAULT_THRESHOLDS`
- Benchmark inputs: `benchmark/cases.jsonl`, evaluated by `benchmark/evaluate.py`
- Platform: Windows 11 (AMD64), CPython 3.12.10
- `SKILL.md` digest: **7145 bytes, `sha256:bd70f42ce11d1713`** — the git blob

On a checkout with CRLF translation (Windows `core.autocrlf=true`) the `SKILL.md` line
instead reads `7291 bytes sha256:a63dd27330017a3c`. That is the same content with line
endings converted, not a different `SKILL.md`; 7145 is the value CI and every Linux and
macOS user sees.

The `commit` and `branch` lines name whichever checkout you ran, so they change between
runs and cannot match a pasted copy forever. Every other line is deterministic for a given
commit. This file is the single source for this output — the README links here instead of
repeating it, precisely because a duplicated copy drifts.

```text
Quantum Reasoning Skill - quickstart verification
--------------------------------------------------------------

[1/4] Checkout identity
    commit      : 9a78b15485c47f78a6274ec4e60470bc150532fd
    VERSION     : 1.1.0
    SKILL.md    : 7145 bytes  sha256:bd70f42ce11d1713
    branch      : docs/readme-truthfulness

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
    skill ver   : 1.1.0   (VERSION)
    commit      : 9a78b15485c47f78a6274ec4e60470bc150532fd
    platform    : Windows 11 (AMD64)
    python      : 3.12.10 (CPython)
    controller  : reference/branch_controller.py DEFAULT_THRESHOLDS
    benchmark   : benchmark/cases.jsonl + benchmark/evaluate.py

RESULT: PASS (structure verified; no performance claim implied)
```

## Reading step 3

The scenario is the README's monolith-migration example. Three things happen:

- `big-bang-rewrite` is **rejected** because its contradiction score is `0.91`, at or above
  the reference reject threshold of `0.85`.
- `feature-flag-carveout` becomes **dormant** because its support score falls below
  `0.35`, and it **revives** once evidence rises by `0.25` (threshold `>= 0.15`). Dormant
  branches are recoverable by design.
- Collapse is **BLOCKED**. `strangler-fig-incremental` leads, but its score is below the
  `0.78` collapse threshold.

That last line is the point. A system tuned to look decisive would have collapsed anyway.
These defaults deliberately refuse to, because nothing in this repository calibrates them.
The weights are documented in [MEASUREMENT.md](MEASUREMENT.md) so they can be measured
rather than trusted.

## Next

- Install the skill in a host: [Getting started](getting-started.md)
- Understand the host requirements: [Compatibility](COMPATIBILITY.md)
- Run a real evaluation: [Benchmark protocol](../benchmark/README.md) and
  [CONTRIBUTING.md](../CONTRIBUTING.md#benchmark-provenance-requirements)