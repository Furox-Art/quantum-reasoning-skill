"""Evaluate baseline and quantum-reasoning runs from JSONL files.

The evaluator uses only the Python standard library. It does not call a model.
External runners can write one result row per case and this script will validate,
score, summarize, and compare those runs without inventing missing measurements.

Results files are untrusted contributed content, so this module treats them as
data only:

* JSON is parsed with :func:`json.loads` and never passed to ``eval``/``exec``;
* input files are read through :func:`benchmark.paths.require_within`, so a
  symlink or ``..`` segment cannot make the evaluator read outside the anchor
  directory (``--cases-dir``, or the current directory when it is not given);
* reads are bounded by ``--max-bytes`` so an oversized submission fails fast
  instead of exhausting memory.

Command-line paths are resolved against the current working directory (or
``--cases-dir``), never against the input file's own parent, so a command copied
out of the README works from a fresh clone. A path that does not exist is a typed
:class:`MissingInputError`: the CLI reports it and exits 2 instead of raising an
uncatchable :class:`FileNotFoundError` traceback. Missing measurements are never
substituted with placeholder rows.
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
from pathlib import Path
from typing import Any, Iterable

try:  # normal package import, and the supported way to reach this module
    from benchmark.paths import require_within
except ImportError:  # pragma: no cover - direct `python benchmark/evaluate.py`
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from benchmark.paths import require_within

DEFAULT_MAX_BYTES = 32 * 1024 * 1024

#: The seed cases that ship with the repository. Used as the ``--cases`` default
#: so the documented command works from a clean checkout.
PACKAGED_CASES = Path(__file__).resolve().parent / "cases.jsonl"

#: Exit code used when a requested input file is missing. Distinct from 1 so a
#: caller can tell "your results file is not there yet" from a validation
#: failure or a crash.
EXIT_MISSING_INPUT = 2

#: Printed with :class:`MissingInputError` so the operator knows what to create.
MISSING_INPUT_HINT = (
    "A results file holds one JSON object per line, e.g. "
    '{"case_id": "case-1", "answer": "42", "tokens": 120, "tool_calls": 0, '
    '"latency_ms": 950}. The evaluator never invents missing measurements; see '
    "benchmark/README.md for the full record contract."
)


class UnsafeJsonError(ValueError):
    """Raised when an input file cannot be read within the configured limits."""


class MissingInputError(ValueError):
    """Raised when a requested input file does not exist (or is not a file)."""


REQUIRED_RESULT_FIELDS = {
    "case_id",
    "answer",
    "tokens",
    "tool_calls",
    "latency_ms",
}

OPTIONAL_TELEMETRY_FIELDS = {
    "branches_total",
    "branches_distinct",
    "revived_branches",
    "recovered_errors",
    "contradictions_found",
    "contradictions_resolved",
}


def read_text_limited(path: Path, max_bytes: int) -> str:
    """Read ``path`` refusing to load more than ``max_bytes`` of text.

    The size is checked before reading so an oversized file never lands in memory.
    A path that does not exist raises the typed :class:`MissingInputError` rather
    than a bare :class:`OSError`, so the CLI can report it as a user error.
    """
    path = Path(path)
    if not path.is_file():
        raise MissingInputError(f"{path}: no such input file")
    size = path.stat().st_size
    if size > max_bytes:
        raise UnsafeJsonError(
            f"{path}: {size} bytes exceeds the {max_bytes} byte limit"
        )
    return path.read_text(encoding="utf-8")


def resolve_input(path: Path, *, cases_dir: Path | None, what: str) -> Path:
    """Resolve one command-line input path and confirm it stays in the anchor.

    The anchor is ``cases_dir`` when given. Without it the documented default
    applies: each input is confined to its own directory. Either way the path is
    resolved against the **current working directory** first, which is what makes
    the commands documented in the README work -- ``benchmark/cases.jsonl`` run
    from the repository root is that file, not a directory nested inside itself.
    """
    raw = Path(path)
    if cases_dir is not None:
        return require_within(cases_dir, raw, what=what)
    target = raw if raw.is_absolute() else Path.cwd() / raw
    return require_within(target.parent, target, what=what)


def read_jsonl(path: Path, *, base: Path | None = None, max_bytes: int = DEFAULT_MAX_BYTES) -> list[dict[str, Any]]:
    """Parse a JSON Lines file into a list of objects.

    ``base`` confines the read to a directory; when omitted the file's own parent
    is used, which keeps relative paths working while still rejecting symlinks
    that point outside that parent.
    """
    anchor = Path(base) if base is not None else Path(path).parent
    resolved = require_within(anchor, path, what="input file")
    text = read_text_limited(resolved, max_bytes)
    rows: list[dict[str, Any]] = []
    for line_number, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line:
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{resolved}:{line_number}: invalid JSON: {exc}") from exc
        if not isinstance(value, dict):
            raise ValueError(f"{resolved}:{line_number}: row must be a JSON object")
        rows.append(value)
    return rows


def normalize_answer(value: Any) -> str:
    return " ".join(str(value).strip().casefold().split())


def validate_case(case: dict[str, Any]) -> None:
    if not isinstance(case, dict):
        raise ValueError("case must be a JSON object")
    for field in ("id", "domain", "prompt", "accepted_answers"):
        if field not in case:
            raise ValueError(f"case missing required field: {field}")
    if not isinstance(case["accepted_answers"], list) or not case["accepted_answers"]:
        raise ValueError(f"case {case['id']!r}: accepted_answers must be a non-empty list")


def validate_result(result: dict[str, Any]) -> None:
    if not isinstance(result, dict):
        raise ValueError("result must be a JSON object")
    missing = REQUIRED_RESULT_FIELDS - set(result)
    if missing:
        raise ValueError(
            f"result {result.get('case_id', '<unknown>')!r} missing fields: "
            + ", ".join(sorted(missing))
        )
    for field in ("tokens", "tool_calls", "latency_ms"):
        value = result[field]
        if not isinstance(value, (int, float)) or isinstance(value, bool) or value < 0:
            raise ValueError(f"result {result['case_id']!r}: {field} must be non-negative")
    for field in OPTIONAL_TELEMETRY_FIELDS:
        if field in result:
            value = result[field]
            if not isinstance(value, (int, float)) or isinstance(value, bool) or value < 0:
                raise ValueError(
                    f"result {result['case_id']!r}: {field} must be non-negative"
                )
    if "branches_distinct" in result and "branches_total" in result:
        if result["branches_distinct"] > result["branches_total"]:
            raise ValueError(
                f"result {result['case_id']!r}: branches_distinct cannot exceed branches_total"
            )
    if "contradictions_resolved" in result and "contradictions_found" in result:
        if result["contradictions_resolved"] > result["contradictions_found"]:
            raise ValueError(
                f"result {result['case_id']!r}: contradictions_resolved cannot exceed contradictions_found"
            )


def answer_is_correct(case: dict[str, Any], answer: Any) -> bool:
    normalized = normalize_answer(answer)
    accepted = {normalize_answer(value) for value in case["accepted_answers"]}
    return normalized in accepted


def safe_mean(values: Iterable[float]) -> float | None:
    materialized = list(values)
    if not materialized:
        return None
    return statistics.fmean(materialized)


def safe_ratio(numerator: float, denominator: float) -> float | None:
    if denominator == 0:
        return None
    return numerator / denominator


def summarize(cases: list[dict[str, Any]], results: list[dict[str, Any]]) -> dict[str, Any]:
    for case in cases:
        validate_case(case)
    for result in results:
        validate_result(result)

    case_by_id = {str(case["id"]): case for case in cases}
    if len(case_by_id) != len(cases):
        raise ValueError("case ids must be unique")

    result_by_id: dict[str, dict[str, Any]] = {}
    for result in results:
        case_id = str(result["case_id"])
        if case_id in result_by_id:
            raise ValueError(f"duplicate result for case_id {case_id!r}")
        if case_id not in case_by_id:
            raise ValueError(f"result references unknown case_id {case_id!r}")
        result_by_id[case_id] = result

    missing_cases = sorted(set(case_by_id) - set(result_by_id))
    evaluated = []
    for case_id, result in result_by_id.items():
        case = case_by_id[case_id]
        evaluated.append((case, result, answer_is_correct(case, result["answer"])))

    total = len(evaluated)
    correct = sum(int(is_correct) for _, _, is_correct in evaluated)

    branch_rows = [
        result
        for _, result, _ in evaluated
        if "branches_total" in result and "branches_distinct" in result
    ]
    contradiction_rows = [
        result
        for _, result, _ in evaluated
        if "contradictions_found" in result and "contradictions_resolved" in result
    ]

    total_branches = sum(row["branches_total"] for row in branch_rows)
    distinct_branches = sum(row["branches_distinct"] for row in branch_rows)
    contradictions_found = sum(row["contradictions_found"] for row in contradiction_rows)
    contradictions_resolved = sum(
        row["contradictions_resolved"] for row in contradiction_rows
    )

    return {
        "cases_defined": len(cases),
        "cases_evaluated": total,
        "missing_case_ids": missing_cases,
        "accuracy": safe_ratio(correct, total),
        "mean_tokens": safe_mean(float(result["tokens"]) for _, result, _ in evaluated),
        "mean_tool_calls": safe_mean(
            float(result["tool_calls"]) for _, result, _ in evaluated
        ),
        "mean_latency_ms": safe_mean(
            float(result["latency_ms"]) for _, result, _ in evaluated
        ),
        "branch_diversity_ratio": safe_ratio(distinct_branches, total_branches),
        "revival_rate_per_case": safe_mean(
            float(result.get("revived_branches", 0)) for _, result, _ in evaluated
        ),
        "error_recovery_rate_per_case": safe_mean(
            float(result.get("recovered_errors", 0)) for _, result, _ in evaluated
        ),
        "contradiction_resolution_rate": safe_ratio(
            contradictions_resolved, contradictions_found
        ),
    }


def percent_change(new: float | None, old: float | None) -> float | None:
    if new is None or old is None or old == 0:
        return None
    return ((new - old) / old) * 100.0


def absolute_change(new: float | None, old: float | None) -> float | None:
    if new is None or old is None:
        return None
    return new - old


def compare(baseline: dict[str, Any], skill: dict[str, Any]) -> dict[str, Any]:
    return {
        "accuracy_delta": absolute_change(skill["accuracy"], baseline["accuracy"]),
        "tokens_percent_change": percent_change(
            skill["mean_tokens"], baseline["mean_tokens"]
        ),
        "tool_calls_percent_change": percent_change(
            skill["mean_tool_calls"], baseline["mean_tool_calls"]
        ),
        "latency_percent_change": percent_change(
            skill["mean_latency_ms"], baseline["mean_latency_ms"]
        ),
        "branch_diversity_delta": absolute_change(
            skill["branch_diversity_ratio"], baseline["branch_diversity_ratio"]
        ),
        "contradiction_resolution_delta": absolute_change(
            skill["contradiction_resolution_rate"],
            baseline["contradiction_resolution_rate"],
        ),
    }


def ensure_finite(value: Any, label: str) -> None:
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError(f"{label} is not finite")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--cases",
        type=Path,
        default=PACKAGED_CASES,
        help=(
            "Path to the benchmark cases JSONL file "
            "(default: the packaged seed cases, benchmark/cases.jsonl)"
        ),
    )
    parser.add_argument("--skill", type=Path, required=True)
    parser.add_argument("--baseline", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--cases-dir",
        type=Path,
        default=None,
        help=(
            "Directory that input files must stay inside. "
            "Defaults to the current working directory."
        ),
    )
    parser.add_argument(
        "--max-bytes",
        type=int,
        default=DEFAULT_MAX_BYTES,
        help="Maximum size in bytes of each input file (default: %(default)s)",
    )
    args = parser.parse_args(argv)

    if args.max_bytes < 1:
        parser.error("--max-bytes must be positive")

    def read_rows(label: str, path: Path) -> list[dict[str, Any]]:
        try:
            resolved = resolve_input(path, cases_dir=args.cases_dir, what=f"--{label}")
            return read_jsonl(resolved, base=args.cases_dir, max_bytes=args.max_bytes)
        except MissingInputError as exc:
            raise MissingInputError(f"--{label}: {exc}") from exc

    # A file the caller named but did not create is a user error, not a crash:
    # report it as one instead of unwinding a FileNotFoundError traceback.
    try:
        cases = read_rows("cases", args.cases)
        skill_results = read_rows("skill", args.skill)
        baseline_results = read_rows("baseline", args.baseline) if args.baseline else None
    except MissingInputError as exc:
        print(f"error: {exc}", file=sys.stderr)
        print(MISSING_INPUT_HINT, file=sys.stderr)
        return EXIT_MISSING_INPUT

    skill_summary = summarize(cases, skill_results)

    payload: dict[str, Any] = {"skill": skill_summary}
    if baseline_results is not None:
        baseline_summary = summarize(cases, baseline_results)
        payload["baseline"] = baseline_summary
        payload["comparison"] = compare(baseline_summary, skill_summary)

    for section_name, section in payload.items():
        if isinstance(section, dict):
            for key, value in section.items():
                ensure_finite(value, f"{section_name}.{key}")

    rendered = json.dumps(payload, indent=2, sort_keys=True)
    print(rendered)
    if args.output:
        output = args.output
        anchor = args.cases_dir if args.cases_dir is not None else Path.cwd()
        resolved_output = require_within(anchor, output, what="--output")
        resolved_output.parent.mkdir(parents=True, exist_ok=True)
        resolved_output.write_text(rendered + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
