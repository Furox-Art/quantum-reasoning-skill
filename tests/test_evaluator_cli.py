"""Regression tests for the documented benchmark command.

The README documents::

    python benchmark/evaluate.py --cases benchmark/cases.jsonl --skill skill-results.jsonl

Two defects made that command unusable from a clean checkout:

1. CLI input paths were anchored at *each input file's own parent directory*, so
   ``benchmark/cases.jsonl`` resolved to ``benchmark/benchmark/cases.jsonl`` and
   raised :class:`FileNotFoundError`;
2. a results file the caller named but had not created yet crashed with a raw
   traceback instead of a typed, friendly error.

Both are pinned here by running the real command through a subprocess against a
copy of the working tree that has no ``.git`` directory -- the closest thing to a
fresh clone. The evaluator must never invent measurements, so the expected
outcome for a missing results file is a typed error and exit code 2, not a
fabricated summary.
"""

from __future__ import annotations

import importlib
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import conftest  # noqa: E402  (repository root is on sys.path only after the insert)

evaluate = importlib.import_module("benchmark.evaluate")

EVALUATOR = ROOT / "benchmark" / "evaluate.py"
CASES = ROOT / "benchmark" / "cases.jsonl"

#: Files that are build/test residue rather than part of a checkout.
IGNORED = shutil.ignore_patterns(
    ".git", "__pycache__", ".mypy_cache", ".ruff_cache", ".pytest_cache", ".coverage"
)

#: Must match ``benchmark.evaluate.EXIT_MISSING_INPUT``.
EXIT_MISSING_INPUT = 2


class CleanCheckout:
    """A copy of the working tree without ``.git`` -- i.e. a fresh clone."""

    def __enter__(self) -> Path:
        self._tmp = tempfile.TemporaryDirectory()
        target = Path(self._tmp.name) / "checkout"
        shutil.copytree(ROOT, target, ignore=IGNORED)
        return target

    def __exit__(self, *exc_info) -> None:
        self._tmp.cleanup()


def seed_case_ids() -> list[str]:
    return [
        json.loads(line)["id"]
        for line in CASES.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


class DocumentedCommandTests(unittest.TestCase):
    """Run the exact commands the docs publish, in a clean copy."""

    def run_command(self, cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(Path("benchmark") / "evaluate.py"), *args],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            check=False,
            timeout=300,
        )

    def write_results(self, cwd: Path, name: str = "skill-results.jsonl") -> Path:
        """Write a valid results file covering every packaged seed case."""
        answers = [
            json.loads(line)["accepted_answers"][0]
            for line in CASES.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        rows = [
            json.dumps(
                {
                    "case_id": case_id,
                    "answer": answer,
                    "tokens": 120,
                    "tool_calls": 0,
                    "latency_ms": 950,
                }
            )
            for case_id, answer in zip(seed_case_ids(), answers)
        ]
        target = cwd / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("\n".join(rows) + "\n", encoding="utf-8")
        return target

    def test_documented_command_reports_a_missing_results_file_gracefully(self):
        """The README command must fail as a typed user error, not a traceback."""
        with CleanCheckout() as cwd:
            result = self.run_command(
                cwd,
                "--cases", "benchmark/cases.jsonl",
                "--skill", "skill-results.jsonl",
            )
        self.assertEqual(result.returncode, EXIT_MISSING_INPUT, result.stdout)
        self.assertNotIn("Traceback", result.stderr)
        self.assertIn("error:", result.stderr)
        self.assertIn("skill-results.jsonl", result.stderr)
        # The operator is told what to create, and that nothing is fabricated.
        self.assertIn("case_id", result.stderr)
        self.assertIn("never invents missing measurements", result.stderr)

    def test_documented_command_reports_a_missing_cases_file_gracefully(self):
        with CleanCheckout() as cwd:
            self.write_results(cwd)
            result = self.run_command(
                cwd,
                "--cases", "benchmark/absent-cases.jsonl",
                "--skill", "skill-results.jsonl",
            )
        self.assertEqual(result.returncode, EXIT_MISSING_INPUT, result.stderr)
        self.assertNotIn("Traceback", result.stderr)
        self.assertIn("--cases", result.stderr)

    def test_documented_command_succeeds_once_the_results_file_exists(self):
        """The regression proper: the same command must exit 0 and print JSON."""
        with CleanCheckout() as cwd:
            self.write_results(cwd)
            result = self.run_command(
                cwd,
                "--cases", "benchmark/cases.jsonl",
                "--skill", "skill-results.jsonl",
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["skill"]["cases_defined"], len(seed_case_ids()))
            self.assertEqual(payload["skill"]["cases_evaluated"], len(seed_case_ids()))
            self.assertEqual(payload["skill"]["missing_case_ids"], [])

    def test_cases_defaults_to_the_packaged_seed_cases(self):
        """``--cases`` is optional: the shipped seed cases are the default."""
        with CleanCheckout() as cwd:
            self.write_results(cwd)
            result = self.run_command(cwd, "--skill", "skill-results.jsonl")
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["skill"]["cases_defined"], len(seed_case_ids()))

    def test_relative_paths_resolve_against_the_working_directory(self):
        """``benchmark/cases.jsonl`` names that file, not a child of itself."""
        with CleanCheckout() as cwd:
            self.write_results(cwd, "nested/skill-results.jsonl")
            result = self.run_command(
                cwd,
                "--cases", "benchmark/cases.jsonl",
                "--skill", "nested/skill-results.jsonl",
                "--output", "summary.json",
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue((cwd / "summary.json").is_file())

    def test_comparison_run_keeps_the_documented_flags(self):
        with CleanCheckout() as cwd:
            self.write_results(cwd)
            self.write_results(cwd, "baseline-results.jsonl")
            result = self.run_command(
                cwd,
                "--cases", "benchmark/cases.jsonl",
                "--baseline", "baseline-results.jsonl",
                "--skill", "skill-results.jsonl",
            )
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertIn("baseline", payload)
        self.assertIn("comparison", payload)
        conftest.assert_close(payload["comparison"]["accuracy_delta"], 0.0)

    def test_module_entry_point_behaves_the_same(self):
        """``python -m benchmark.evaluate`` is the other documented form."""
        with CleanCheckout() as cwd:
            self.write_results(cwd)
            result = subprocess.run(
                [
                    sys.executable, "-m", "benchmark.evaluate",
                    "--cases", "benchmark/cases.jsonl",
                    "--skill", "skill-results.jsonl",
                ],
                cwd=str(cwd),
                capture_output=True,
                text=True,
                check=False,
                timeout=300,
            )
        self.assertEqual(result.returncode, 0, result.stderr)


class MissingInputErrorTests(unittest.TestCase):
    """The typed error itself, exercised in-process."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.base = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_missing_file_raises_the_typed_error(self):
        with self.assertRaises(evaluate.MissingInputError):
            evaluate.read_text_limited(self.base / "absent.jsonl", 1024)

    def test_typed_error_is_a_value_error(self):
        self.assertTrue(issubclass(evaluate.MissingInputError, ValueError))

    def test_a_directory_is_not_an_input_file(self):
        with self.assertRaises(evaluate.MissingInputError):
            evaluate.read_text_limited(self.base, 1024)

    def test_existing_file_still_reads(self):
        target = self.base / "rows.jsonl"
        target.write_text('{"case_id": "c1"}\n', encoding="utf-8")
        self.assertEqual(
            evaluate.read_text_limited(target, 1024), '{"case_id": "c1"}\n'
        )

    def test_main_returns_the_typed_exit_code(self):
        import contextlib
        import io

        buffer = io.StringIO()
        with contextlib.redirect_stderr(buffer):
            code = evaluate.main(["--skill", str(self.base / "absent.jsonl")])
        self.assertEqual(code, EXIT_MISSING_INPUT)
        self.assertIn("no such input file", buffer.getvalue())


if __name__ == "__main__":
    unittest.main()
