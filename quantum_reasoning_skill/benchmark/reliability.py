"""Synthetic score-outcome reliability diagnostic for the benchmark harness.

**Everything this module measures is synthetic.** Scores and outcomes are
produced by a seeded pseudo-random generator whose calibration is known by
construction; no language model is called and no real task is evaluated. The
diagnostic exists to check the harness's *measurement machinery* -- binning,
expected calibration error (ECE) and Brier score -- against data with a known
answer, the same way the seed cases check that the evaluator runs. It supports
**no claim that this skill improves any model's reasoning**, and its numbers
must never be cited as model performance.

What it can show:

* with ``miscalibration=0`` the outcome probability equals the score, so a
  correct reliability measurement reports a small ECE (sampling noise only);
* with a nonzero ``miscalibration`` shift the outcomes are systematically
  more (or less) frequent than the scores claim, so a correct measurement
  reports a clearly larger ECE. That is the negative control: a diagnostic
  that cannot detect known miscalibration must not be trusted on real data.

What it cannot show: anything about a language model. A real baseline-vs-skill
evaluation is still pending and is community-run; see the README's
"Benchmark status" section and CONTRIBUTING.md's provenance requirements.

Both entry points work, mirroring the evaluator:
``python quantum_reasoning_skill/benchmark/reliability.py`` and
``python -m quantum_reasoning_skill.benchmark.reliability``. Output is
deterministic for a given seed: no wall clock, no hash-order dependence,
keys sorted at render time.
"""

from __future__ import annotations

import argparse
import json
import math
import random
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

try:  # normal package import, and the supported way to reach this module
    from quantum_reasoning_skill.benchmark.paths import require_within
except ImportError:  # pragma: no cover - direct `python .../benchmark/reliability.py`
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from quantum_reasoning_skill.benchmark.paths import require_within

#: Default seed for the synthetic generator. Fixed so every run is reproducible.
DEFAULT_SEED = 2026

#: Default number of synthetic (score, outcome) pairs.
DEFAULT_SAMPLES = 10_000

#: Default number of equal-width reliability bins over [0, 1].
DEFAULT_BINS = 10

#: Printed next to every number this module produces, in the artifact itself.
SYNTHETIC_DISCLAIMER = (
    "Synthetic diagnostic: scores and outcomes come from a seeded pseudo-random "
    "generator, not from any language model or real task. It checks the harness's "
    "calibration measurement machinery only and supports no claim about reasoning "
    "performance."
)

#: Exit code for user errors (bad arguments, an output path outside the anchor),
#: matching the evaluator's convention so callers can tell them from crashes.
EXIT_USER_ERROR = 2


def generate_synthetic_pairs(
    seed: int, samples: int, *, miscalibration: float = 0.0
) -> list[tuple[float, int]]:
    """Generate ``samples`` synthetic (score, outcome) pairs, deterministically.

    Scores are uniform on [0, 1). Outcomes are Bernoulli draws with probability
    ``clip(score + miscalibration, 0, 1)``: with a zero shift the generator is
    perfectly calibrated by construction, and a nonzero shift makes it
    systematically over- or under-confident so the diagnostic has a known defect
    to detect.
    """
    if samples < 1:
        raise ValueError(f"samples must be at least 1, got {samples}")
    if not math.isfinite(miscalibration) or abs(miscalibration) > 1.0:
        raise ValueError(
            f"miscalibration must be finite and within [-1, 1], got {miscalibration!r}"
        )
    rng = random.Random(seed)
    pairs: list[tuple[float, int]] = []
    for _ in range(samples):
        score = rng.random()
        probability = min(1.0, max(0.0, score + miscalibration))
        outcome = int(rng.random() < probability)
        pairs.append((score, outcome))
    return pairs


def _validate_pair(pair: Any, index: int) -> tuple[float, int]:
    """Fail closed on anything that is not a (score in [0, 1], outcome in {0, 1}).

    Wrong types raise :class:`TypeError`, wrong values :class:`ValueError`, so a
    caller can tell a malformed record from an out-of-range measurement.
    """
    if not isinstance(pair, (tuple, list)):
        raise TypeError(f"pair {index} must be a (score, outcome) pair, got {pair!r}")
    if len(pair) != 2:
        raise ValueError(f"pair {index} must have exactly 2 elements, got {len(pair)}")
    score, outcome = pair
    if isinstance(score, bool) or not isinstance(score, (int, float)):
        raise TypeError(f"pair {index}: score must be a number, got {score!r}")
    if not math.isfinite(score) or not 0.0 <= score <= 1.0:
        raise ValueError(f"pair {index}: score must be finite and in [0, 1], got {score!r}")
    if isinstance(outcome, bool) or not isinstance(outcome, int):
        raise TypeError(f"pair {index}: outcome must be an integer, got {outcome!r}")
    if outcome not in (0, 1):
        raise ValueError(f"pair {index}: outcome must be 0 or 1, got {outcome!r}")
    return float(score), outcome


def reliability_diagnostic(
    pairs: Sequence[tuple[float, int]], *, bins: int = DEFAULT_BINS
) -> dict[str, Any]:
    """Measure score-outcome reliability on ``pairs`` with equal-width bins.

    Returns per-bin counts, mean score and observed outcome rate (``None`` for
    an empty bin -- "not measured", never a fabricated zero), plus the overall
    expected calibration error (count-weighted mean absolute gap between mean
    score and outcome rate) and Brier score. Inputs are validated fail-closed:
    an invalid pair raises :class:`ValueError` instead of being silently binned.
    """
    if bins < 1:
        raise ValueError(f"bins must be at least 1, got {bins}")
    if not pairs:
        raise ValueError("pairs must not be empty")
    validated = [_validate_pair(pair, index) for index, pair in enumerate(pairs)]

    counts = [0] * bins
    score_sums = [0.0] * bins
    outcome_sums = [0] * bins
    for score, outcome in validated:
        # score == 1.0 belongs to the last bin, not to a bin of its own.
        index = min(int(score * bins), bins - 1)
        counts[index] += 1
        score_sums[index] += score
        outcome_sums[index] += outcome

    total = len(validated)
    rows: list[dict[str, Any]] = []
    ece = 0.0
    for index in range(bins):
        count = counts[index]
        mean_score = score_sums[index] / count if count else None
        outcome_rate = outcome_sums[index] / count if count else None
        if count:
            ece += count * abs(score_sums[index] / count - outcome_sums[index] / count)
        rows.append(
            {
                "bin": f"{index / bins:.3f}-{(index + 1) / bins:.3f}",
                "count": count,
                "mean_score": mean_score,
                "outcome_rate": outcome_rate,
            }
        )

    return {
        "samples": total,
        "bin_count": bins,
        "bins": rows,
        "expected_calibration_error": ece / total,
        "brier_score": sum((score - outcome) ** 2 for score, outcome in validated) / total,
        "mean_score": sum(score for score, _ in validated) / total,
        "outcome_rate": sum(outcome for _, outcome in validated) / total,
    }


def run_synthetic_diagnostic(
    *,
    seed: int = DEFAULT_SEED,
    samples: int = DEFAULT_SAMPLES,
    bins: int = DEFAULT_BINS,
    miscalibration: float = 0.0,
) -> dict[str, Any]:
    """Run the full synthetic diagnostic and label the artifact as synthetic.

    The payload carries ``"synthetic": true`` and a disclaimer next to every
    number, so a downstream reader cannot mistake it for a model evaluation.
    """
    pairs = generate_synthetic_pairs(seed, samples, miscalibration=miscalibration)
    diagnostic = reliability_diagnostic(pairs, bins=bins)
    return {
        "diagnostic": "score-outcome-reliability",
        "synthetic": True,
        "data": "synthetic",
        "disclaimer": SYNTHETIC_DISCLAIMER,
        "generator": {
            "seed": seed,
            "samples": samples,
            "miscalibration_shift": miscalibration,
            "outcome_model": "outcome ~ Bernoulli(clip(score + shift, 0, 1)); "
            "score ~ Uniform(0, 1)",
        },
        **diagnostic,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Synthetic score-outcome reliability diagnostic. Generates seeded "
            "pseudo-random scores and outcomes (no model, no real task) and checks "
            "that the reliability measurement detects known miscalibration. "
            "Supports no performance claim."
        )
    )
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED, help="generator seed")
    parser.add_argument(
        "--samples", type=int, default=DEFAULT_SAMPLES, help="number of synthetic pairs"
    )
    parser.add_argument(
        "--bins", type=int, default=DEFAULT_BINS, help="equal-width reliability bins"
    )
    parser.add_argument(
        "--miscalibration",
        type=float,
        default=0.0,
        help=(
            "known calibration defect to inject: outcome probability becomes "
            "clip(score + shift, 0, 1). 0 is perfectly calibrated by construction; "
            "a nonzero shift must raise the measured ECE (negative control)"
        ),
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="optional JSON artifact path; must stay inside the working directory",
    )
    args = parser.parse_args(argv)

    if args.samples < 1:
        parser.error("--samples must be at least 1")
    if args.bins < 1:
        parser.error("--bins must be at least 1")
    if not math.isfinite(args.miscalibration) or abs(args.miscalibration) > 1.0:
        parser.error("--miscalibration must be finite and within [-1, 1]")

    payload = run_synthetic_diagnostic(
        seed=args.seed,
        samples=args.samples,
        bins=args.bins,
        miscalibration=args.miscalibration,
    )
    rendered = json.dumps(payload, indent=2, sort_keys=True)
    print(rendered)
    if args.output:
        try:
            resolved = require_within(Path.cwd(), args.output, what="--output")
        except ValueError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return EXIT_USER_ERROR
        resolved.parent.mkdir(parents=True, exist_ok=True)
        resolved.write_text(rendered + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
