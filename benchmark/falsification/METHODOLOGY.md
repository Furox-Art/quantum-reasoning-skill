# Falsification benchmark methodology

This document describes the falsification-scenario comparative benchmark in
`benchmark/falsification/`: what it measures, how the numbers are produced, and
the exact commands needed to reproduce them. Every number in
`benchmark/falsification/results/` comes from running the suite in this
repository. Nothing in this document is hand-computed.

## What this benchmark is (and is not)

This is a **controller benchmark**. It compares two deterministic reasoning
policies over identical, hand-crafted evidence streams:

- **single-hypothesis**: commits to the strongest branch at the first evidence
  step and never revisits it.
- **multi-hypothesis**: the reference branch controller in
  `reference/branch_controller.py`, which scores branches from explicit metric
  snapshots, prunes contradicted branches, revives dormant branches on material
  evidence change, and answers with the surviving leader.

Both policies see the same scenario data in the same order with the same compute
budget formula. The only difference is the decision policy.

It is **not** a measurement of any language model. No LLM is called, no API key
is required, and no network access occurs. The evidence streams are synthetic
branch-metric snapshots, so these results are a statement about the reference
decision logic under curated inputs. They cannot support any claim about
model-level reasoning performance, and they should not be quoted as if they did.
A separate model-level benchmark (running the same scenarios as prompts against
real providers) is future work; see "Limitations" below.

## Scenario set

Nine deterministic scenarios in three families:

| family | count | what it tests |
|---|---:|---|
| falsification | 4 | the initially strongest hypothesis is contradicted midway; the system must abandon it and switch to the correct alternative |
| revival | 3 | the correct hypothesis is dormant or rejected early and must be re-evaluated when later evidence materially improves it |
| control | 2 | the first hypothesis is correct throughout; a good system must not lose ground here |

Every scenario has a known ground-truth branch (`truth_branch`), an exact-match
answer, and an explicit evidence-step stream. Each step records a full
branch-metric snapshot (`evidence`, `verification`, `independence`,
`information_gain`, `contradiction`, `unresolved_assumptions`, `normalized_cost`,
`shared_assumption_ratio`, `semantic_similarity_to_leader`) plus whether the
ground-truth answer is knowable from that step.

Scenario definitions live in `benchmark/falsification/scenarios.py`. They are
literal Python data (no randomness, no fixed-seed generation, no external
files), so a scenario always produces the same run. `tests/test_falsification_suite.py`
asserts every metric stays in `[0, 1]` and that falsification scenarios really do
cross the rejection threshold at their declared falsification step.

### The four falsification scenarios

- `falsification-001` — Simpson-style reversal. The pooled-trend hypothesis
  leads early; a segment split at step 3 reverses the sign.
- `falsification-002` — security triage. A recent config change looks like the
  cause until audit logs at step 3 place access outside the change window.
- `falsification-003` — debugging. A stack trace points inside a library until a
  minimal reproduction without that library also fails at step 3.
- `falsification-004` — late falsification. The wrong hypothesis leads for three
  of five steps and is only falsified at step 4, so it tests whether the system
  keeps alternatives alive *before* it needs them.

### The three revival scenarios

- `revival-001` — the correct hypothesis drops below the dormant threshold at
  step 2 and regains a material evidence increase at step 3.
- `revival-002` — the correct hypothesis is weakest of three, then gains an
  independent verification jump (>= 0.25) at step 3.
- `revival-003` — rejected-branch reopen. The correct hypothesis is rejected at
  step 2 on a conflicting observation that is itself retracted at step 3. The
  reference controller never auto-revives a rejected branch, so the runner must
  explicitly reopen it when the rejection premise is invalidated; this scenario
  tests that path.

### The two control scenarios

`control-001` and `control-002` have a correct, stable leader and no
contradiction. They exist so the falsification gain cannot come from
"multi-hypothesis is better at everything" — the comparison must be
interpretable only where the scenario actually contains a falsification event.

## Metric definitions

All metrics are computed by `benchmark/falsification/run_suite.py`.

**Final accuracy.** Fraction of scenarios whose final answer (the leader at the
last evidence step) equals the ground-truth branch. Reported overall and
per-scenario-family.

**Decision-switch success rate.** Over falsification scenarios only. A switch is
counted as successful when the leader stopped being the falsified decoy within
`SWITCH_WINDOW = 1` evidence steps after the decoy first crossed the rejection
threshold (`contradiction >= 0.85`). The switch delay is the number of evidence
steps between the falsification step and the first step whose leader is the
correct branch.

**Revival success rate.** Over revival scenarios only. Counted as successful
when the designated revival branch is non-rejected at or after the scenario's
revival step.

**Confidence calibration — Brier score.** The multiclass Brier score over every
step at which an answer is committed (`answer_known_from` is true). For each such
step the runner reports a probability vector over all branches, derived
deterministically from each branch's support score with a softmax at temperature
`0.15`. The score is

```
brier = mean over committed steps and branches of (p_reported - outcome)^2
```

with `outcome = 1` for the truth branch and `0` otherwise. Lower is better; a
perfect confident answer scores 0 and a confidently wrong answer approaches 2.
`reliability_bins` in `results.json` buckets the reported truth-branch
probability into 0.2-wide bins for reliability-curve inspection.

**Latency.** Measured wall-clock milliseconds per decision using
`time.perf_counter()` around the per-step policy update. Because the multi policy
keeps more branches alive, its per-decision work is larger; the absolute values
are machine-dependent and only the ratio is meaningful.

**Token cost.** A deterministic model, not a real tokenizer:

```
tokens_per_step = tokens_per_decision + tokens_per_branch_step * (active + dormant)
                  + tokens_per_verification_step * active
```

with `tokens_per_decision = 8`, `tokens_per_branch_step = 12`,
`tokens_per_verification_step = 6`. Cost differences therefore come only from
how many branches each policy keeps alive, which is the quantity of interest. A
real model run would substitute measured token counts.

## Reproduction

From the repository root, with Python 3.10 or newer and no extra dependencies:

```bash
# run the suite; regenerates results.json, RESULTS.md and scenarios.jsonl
python benchmark/falsification/run_suite.py

# run the full test suite (includes the falsification tests)
python -m unittest discover -s tests

# run only the falsification tests
python -m unittest tests.test_falsification_suite -v
```

Deterministic fields (accuracy, switch success, revival success, Brier score,
token counts, switch delay) are identical on every run and machine. Latency is
wall-clock and therefore varies slightly; it is reported for cost-comparison
context only, and the test suite deliberately does not assert on it.

## Results

Headline numbers from the committed run (`benchmark/falsification/results/`):

| metric | single-hypothesis | multi-hypothesis |
|---|---:|---:|
| overall accuracy | 0.222 | 1.000 |
| falsification-scenario accuracy | 0.000 | 1.000 |
| decision-switch success rate | 0.000 | 1.000 |
| mean switch delay (evidence steps) | n/a | 0.000 |
| revival success rate | 0.000 | 1.000 |
| control-scenario accuracy | 1.000 | 1.000 |
| Brier score (lower is better) | 0.033 | 0.033 |
| mean tokens per scenario | 115.6 | 242.2 |

Latency is omitted from the table above because it is wall-clock and
machine-dependent; `results.json` records the value from the committed run
(0.012 ms and 0.050 ms per decision on the author's machine) and any
reproduction will legitimately differ. Only the deterministic metrics above
are stable across machines.

Reading of these numbers:

- The single-hypothesis policy fails all four falsification scenarios and all
  three revival scenarios, and passes both control scenarios. It gets 2/9 = 22%.
- The multi-hypothesis policy gets 9/9. It abandons the falsified decoy at the
  same step the falsification arrives (delay 0 steps) in all four falsification
  scenarios, and revives the required branch in all three revival scenarios.
- The accuracy delta is +0.778 overall and +1.000 on falsification scenarios.
- Calibration is a **null result**: Brier scores are statistically identical
  (0.0326 vs 0.0328; the multi policy is 0.0001 *worse*). The Brier score is
  dominated by the revival and control scenarios, where both policies report
  the same probability vectors because both use the same score-to-probability
  mapping over the same metrics. The falsification scenarios do show the
  expected directional separation but are too few to move the aggregate. This
  benchmark does not demonstrate better confidence calibration, and the README
  claim does not include calibration.
- The cost is real: +109.6% tokens per scenario (115.6 -> 242.2). The
  accuracy gain is not free.

## Limitations

- **Not a model benchmark.** No language model is involved. These results
  measure the reference decision controller on synthetic evidence streams. They
  say nothing about how any LLM reasons.
- **Synthetic evidence, not model telemetry.** The metric snapshots are
  authored, not measured from real reasoning traces. A policy that performs
  perfectly here can still fail on real inputs where evidence arrives noisily,
  metrics are mis-estimated, or the decoy is never formally contradicted (the
  falsification-004 case where `contradiction` never reaches 0.85).
- **Small n.** Nine scenarios, four in the decisive falsification family. The
  reported rates are 0/4 and 4/4, which are exact for this set but have wide
  confidence intervals; do not read 100% as a population rate.
- **Calibration is unmeasured, not good.** The Brier score shows no difference.
  Any calibration claim would need scenarios where the two policies report
  genuinely different probability vectors.
- **Cost is modelled, not measured.** Token counts come from a fixed formula.
- **Latency is machine-dependent** and only useful as a ratio.
- **No held-out split.** The scenarios are also the scenarios used to confirm the
  controller's behaviour, so there is no train/test separation. A future
  calibration pass must use a separate development set, as `docs/MEASUREMENT.md`
  already requires.

## Relationship to the existing benchmark

This suite extends `benchmark/`; it does not replace it.

- `benchmark/evaluate.py` compares real model runs recorded as JSONL. This
  falsification suite needs no model and compares decision policies directly.
- `benchmark/falsification/scenarios.jsonl` is emitted in the same case-record
  format as `benchmark/cases.jsonl`, so these scenarios can be fed to
  `benchmark/evaluate.py` unchanged when real model runs become available.
- The community-result submission policy in `benchmark/README.md` is unchanged;
  this suite's artifacts are maintained in-repo, not submitted as a community
  result.

## Files

```
benchmark/falsification/scenarios.py        # deterministic scenario definitions
benchmark/falsification/run_suite.py        # policies, metrics, aggregator, CLI
benchmark/falsification/scenarios.jsonl     # generated case records (committed)
benchmark/falsification/results/results.json # full machine-readable results
benchmark/falsification/results/RESULTS.md   # human-readable results table
benchmark/falsification/METHODOLOGY.md      # this file
tests/test_falsification_suite.py           # unit tests for the suite
```
