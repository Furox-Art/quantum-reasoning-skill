"""Validate reproducible community benchmark result bundles.

Community bundles arrive from pull requests, so everything they contain is
untrusted input. The validator therefore:

* imports :mod:`benchmark.evaluate` through the package, so a local ``evaluate.py``
  or an unrelated third-party distribution of the same name cannot shadow it;
* resolves every bundle member and refuses anything that escapes the bundle
  directory, including symlinks pointing outside it;
* parses JSON with :func:`json.loads` only -- no ``eval``, ``exec``, ``pickle``,
  ``yaml.load`` or other deserialisation of contributed data;
* bounds file sizes so a large submission fails fast.
"""
from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path
try:  # `python -m benchmark.validate_submission`
    from benchmark import evaluate
    from benchmark.paths import PathBoundaryError, safe_bundle_member
except ImportError:  # `python benchmark/validate_submission.py`
    # Running as a script puts ``benchmark/`` on sys.path, not the repository
    # root, so the package-qualified import above cannot resolve. Anchor the
    # repository root and import the same package modules, rather than falling
    # back to a bare ``import evaluate`` that any module named ``evaluate`` on
    # sys.path could satisfy.
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from benchmark import evaluate
    from benchmark.paths import PathBoundaryError, safe_bundle_member

REQUIRED_FILES = {"metadata.json", "cases.jsonl", "baseline.jsonl", "skill.jsonl", "comparison.json", "README.md"}
COND_FIELDS = {"instruction_config", "sampling", "tool_availability", "context_limit", "output_limit"}
META_FIELDS = {"provider", "model", "run_date", "skill_version", "repetitions_per_case", "baseline", "skill", "failures_recorded"}


def load_json(path: Path, *, max_bytes: int = evaluate.DEFAULT_MAX_BYTES) -> object:
    """Parse a JSON file with no deserialisation beyond the JSON grammar."""
    try:
        text = evaluate.read_text_limited(path, max_bytes)
    except OSError as exc:
        raise ValueError(f"{path}: unreadable: {exc}") from exc
    except evaluate.UnsafeJsonError as exc:
        raise ValueError(str(exc)) from exc
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{path}: invalid JSON: {exc}") from exc


def validate_metadata(meta: object) -> None:
    if not isinstance(meta, dict):
        raise ValueError("metadata.json must contain a JSON object")
    missing = META_FIELDS - set(meta)
    if missing:
        raise ValueError(f"metadata.json missing fields: {sorted(missing)}")
    for key in ("provider", "model", "skill_version"):
        if not isinstance(meta[key], str) or not meta[key].strip():
            raise ValueError(f"metadata.{key} must be a non-empty string")
    if not isinstance(meta["run_date"], str):
        raise ValueError("metadata.run_date must be YYYY-MM-DD")
    try:
        date.fromisoformat(meta["run_date"])
    except ValueError as exc:
        raise ValueError("metadata.run_date must be YYYY-MM-DD") from exc
    repetitions = meta["repetitions_per_case"]
    if not isinstance(repetitions, int) or isinstance(repetitions, bool) or repetitions < 1:
        raise ValueError("metadata.repetitions_per_case must be >= 1")
    if meta["failures_recorded"] is not True:
        raise ValueError("metadata.failures_recorded must be true")
    for name in ("baseline", "skill"):
        value = meta[name]
        if not isinstance(value, dict):
            raise ValueError(f"metadata.{name} must be an object")
        missing_cond = COND_FIELDS - set(value)
        if missing_cond:
            raise ValueError(f"metadata.{name} missing fields: {sorted(missing_cond)}")
        if not isinstance(value["instruction_config"], str) or not value["instruction_config"].strip():
            raise ValueError(f"metadata.{name}.instruction_config must be non-empty")
        if not isinstance(value["sampling"], dict):
            raise ValueError(f"metadata.{name}.sampling must be an object")
        for limit in ("context_limit", "output_limit"):
            v = value[limit]
            if v is not None and (
                not isinstance(v, int) or isinstance(v, bool) or v < 1
            ):
                raise ValueError(f"metadata.{name}.{limit} must be null or >= 1")


def _case_map(cases):
    out = {}
    for case in cases:
        evaluate.validate_case(case)
        cid = str(case["id"])
        if cid in out:
            raise ValueError(f"duplicate case id: {cid}")
        out[cid] = case
    return out


def validate_bundle(bundle: Path) -> None:
    """Validate one bundle directory.

    ``bundle`` is resolved once and every member is looked up through
    :func:`safe_bundle_member`, so neither the directory nor its contents can
    redirect the validator outside the bundle.
    """
    root = Path(bundle).resolve()
    try:
        present = {p.name for p in root.iterdir() if p.is_file()}
    except OSError as exc:
        raise ValueError(f"{bundle}: unreadable bundle directory: {exc}") from exc
    missing = REQUIRED_FILES - present
    if missing:
        raise ValueError(f"{bundle}: missing files: {sorted(missing)}")

    def member(name: str) -> Path:
        try:
            return safe_bundle_member(root, name)
        except (PathBoundaryError, ValueError) as exc:
            raise ValueError(f"{bundle}: {exc}") from exc

    validate_metadata(load_json(member("metadata.json")))
    cases = evaluate.read_jsonl(member("cases.jsonl"), base=root)
    case_by_id = _case_map(cases)
    baseline = evaluate.read_jsonl(member("baseline.jsonl"), base=root)
    skill = evaluate.read_jsonl(member("skill.jsonl"), base=root)
    for row in baseline + skill:
        evaluate.validate_result(row)
    for label, rows in (("baseline", baseline), ("skill", skill)):
        ids = [str(r["case_id"]) for r in rows]
        if len(ids) != len(set(ids)):
            raise ValueError(f"{bundle}: duplicate {label} case_id")
        if set(ids) != set(case_by_id):
            raise ValueError(f"{bundle}: {label} must contain exactly one row for every case")
    expected = {
        "skill": evaluate.summarize(cases, skill),
        "baseline": evaluate.summarize(cases, baseline),
    }
    expected["comparison"] = evaluate.compare(expected["baseline"], expected["skill"])
    submitted = load_json(member("comparison.json"))
    if submitted != expected:
        raise ValueError(f"{bundle}: comparison.json does not match evaluator recomputation")
    if not load_text(member("README.md")).strip():
        raise ValueError(f"{bundle}: README.md must not be empty")


def load_text(path: Path, *, max_bytes: int = evaluate.DEFAULT_MAX_BYTES) -> str:
    """Read a bundle text file under the same size bound as the JSON artifacts."""
    try:
        return evaluate.read_text_limited(path, max_bytes)
    except OSError as exc:
        raise ValueError(f"{path}: unreadable: {exc}") from exc
    except evaluate.UnsafeJsonError as exc:
        raise ValueError(str(exc)) from exc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("benchmark/results/community"))
    parser.add_argument("--allow-empty", action="store_true")
    args = parser.parse_args(argv)
    root = args.root
    if not root.exists():
        if args.allow_empty:
            return 0
        raise SystemExit(f"community benchmark root not found: {root}")
    try:
        bundles = sorted(p for p in root.iterdir() if p.is_dir())
    except OSError as exc:
        raise SystemExit(
            f"community benchmark root not readable: {root}: {exc}"
        ) from exc
    if not bundles and not args.allow_empty:
        raise SystemExit("no community benchmark bundles found")
    for bundle in bundles:
        validate_bundle(bundle)
        print(f"validated {bundle}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
