# Measurement and branch-control specification

This document turns the qualitative protocol in `SKILL.md` into an auditable reference policy. It does **not** claim that these constants are optimal or scientifically validated. They are initial defaults that must be calibrated against benchmark data.

**Calibration status: nothing in this document has been calibrated.** Every weight and
threshold below is transcribed from `DEFAULT_THRESHOLDS` and `WEIGHTS` in
[`../quantum_reasoning_skill/reference/branch_controller.py`](../quantum_reasoning_skill/reference/branch_controller.py) and is unchanged by
`SKILL.md`. They are specified so they can be measured and replaced, not because they have
been tuned. [`quickstart.md`](quickstart.md) step 3 shows the practical consequence: with
defensible inputs the controller refuses to collapse, because the leader falls short of the
collapse threshold.

**No benchmark result in this repository has been produced with these constants.** See
[the benchmark status section](../README.md#benchmark-status).

## 1. Observable branch metrics

Each branch is represented by normalized values in `[0, 1]`:

- `evidence`: support from verified facts or observations
- `verification`: strength of independent checks
- `independence`: independence from other branches
- `information_gain`: expected value of further work on the branch
- `contradiction`: severity of conflict with verified facts
- `unresolved_assumptions`: remaining unsupported assumptions
- `normalized_cost`: relative compute/tool cost already consumed
- `shared_assumption_ratio`: overlap in critical assumptions with the current leader
- `semantic_similarity_to_leader`: redundancy signal for near-duplicate branches

These values are control metadata. They must not require exposing private chain-of-thought.

## 2. Correlation penalty

A branch should not receive full independence credit when it shares assumptions or is effectively a paraphrase of the leader.

```text
correlation = max(shared_assumption_ratio, semantic_similarity_to_leader)
effective_independence = independence * (1 - correlation)
```

## 3. Reference support score

The reference implementation uses:

```text
score = clamp01(
    0.15
  + 0.25 * evidence
  + 0.25 * verification
  + 0.15 * effective_independence
  + 0.10 * information_gain
  - 0.15 * contradiction
  - 0.05 * unresolved_assumptions
  - 0.05 * normalized_cost
)
```

The weights are deliberately explicit so they can be benchmarked and changed. They are not hidden policy.

## 4. State transitions

Reference defaults:

- reject when `contradiction >= 0.85`
- move to dormant when `score < 0.35`
- otherwise keep active

A dormant branch is revived when at least one material change occurs relative to its previous measurement:

- evidence increases by `>= 0.15`, or
- verification increases by `>= 0.25`, or
- contradiction decreases by `>= 0.20`

A rejected branch is not automatically revived by the reference controller. A caller may explicitly reopen it if the supposedly verified fact that caused rejection is itself invalidated.

## 5. Dynamic search width

Uncertainty is estimated from the normalized Shannon entropy of surviving branch scores.

Reference width policy:

| uncertainty | branch range |
|---|---:|
| `< 0.25` | 2–3 |
| `0.25–0.55` | 4–6 |
| `>= 0.55` | 6–10 |

This is a compute-allocation recommendation, not a requirement to generate the maximum branch count.

## 6. Collapse criteria

The reference controller permits collapse only when all applicable checks pass:

1. leader score `>= 0.78`
2. leader verification `>= 0.75`
3. leader contradiction `<= 0.15`
4. no unresolved high-information alternative remains close enough to plausibly change the outcome
5. if a runner-up exists, leader margin `>= 0.12`

Check 4 is evaluated **before** check 5, and that order is load-bearing. A runner-up is
"high-information" when its `information_gain >= 0.60`, and "close enough" when the leader
margin is `<= 0.10`. Because `0.10` sits inside the generic `0.12` margin band, any runner-up
that satisfies check 4 also satisfies check 5 — so evaluating the generic margin first made
check 4 unreachable and reported the weaker "leader margin is too small" reason instead of the
specific one. Both outcomes block collapse, but only the specific reason tells an operator that
further work on the runner-up, not more evidence for the leader, is what keeps the search open.

If these checks fail, the system should continue verification, keep multiple surviving alternatives, or report unresolved alternatives rather than manufacture certainty.

### Numeric tolerance for artifact comparisons

The suite's own comparisons use one absolute tolerance, `conftest.NUMERIC_TOLERANCE = 1e-6`.
Committed artifacts round their floats to six decimals (`brier`, `latency_ms`, `leader_score`,
`probabilities`), while the reliability-bin `truth_probability` is stored at full precision; on
one machine, stored-vs-recomputed `brier` differs by up to `4.9e-7` and stored-vs-recomputed
`truth_probability` by up to `3.4e-16`. Exact equality would reject artifacts that are correct,
and `assertAlmostEqual`'s seven-decimal default is a second undocumented tolerance. Every
numeric comparison in the tests therefore goes through `conftest.assert_close`.

## 7. Diversity diagnostic

Given pairwise semantic similarities, a pair is treated as redundant when similarity is `>= 0.85` by default.

```text
diversity_ratio = materially_distinct_pairs / all_measured_pairs
```

This metric is intentionally simple. Embedding model choice, similarity calibration and domain effects must be reported by any experiment that uses it.

## 8. What must be calibrated

Benchmarking should test at least:

- score weights
- contradiction rejection threshold
- dormant threshold
- revival deltas
- collapse score and margin
- semantic duplicate threshold
- uncertainty-to-width mapping

Calibration must use a development set separate from final held-out evaluation.

## 9. Failure modes to measure

A serious evaluation should label and count:

- early lock-in
- duplicated branches
- shared-assumption failure
- false contradiction detection
- failure to revive a correct dormant branch
- excessive search after the answer is already established
- premature collapse
- tool-confirmation bias
- accuracy gain that is explained only by substantially higher compute

## 10. Reproducibility rule

Any reported improvement must include the baseline configuration and raw aggregate result files needed to reproduce the comparison. Do not publish only a selected percentage or a hand-picked example.
