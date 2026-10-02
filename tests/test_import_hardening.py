"""Regression tests for the benchmark package import boundary.

The validator used to do a bare ``import evaluate``, which resolves against
``sys.path``. Any ``evaluate.py`` in the current working directory, on
``PYTHONPATH``, or provided by an unrelated distribution (there is a real
``evaluate`` package on PyPI) would be imported and executed instead of the
repository's own evaluator.

``benchmark`` is now a real package and the modules import it absolutely, so the
tests below pin that behaviour down.
"""

from __future__ import annotations

import importlib
import importlib.util
import os
import subprocess  # nosec B404 - fixed argv, never shell=True; see run_isolated()
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

HOSTILE = "raise SystemExit('HIJACKED_BY_HOSTILE_MODULE')\n"

# These tests spawn subprocesses on purpose: the only way to prove that a hostile
# sys.path entry cannot shadow the package is to run the interpreter with that
# entry present. Every call below passes an explicit argument vector with
# ``shell`` left at its default (False), so no shell parses the arguments and no
# input reaches a command line from bundle content.


class PackageBoundaryTests(unittest.TestCase):
    def test_benchmark_is_a_real_package(self):
        self.assertTrue((ROOT / "benchmark" / "__init__.py").is_file())

    def test_evaluate_resolves_to_the_repository_copy(self):
        module = importlib.import_module("benchmark.evaluate")
        self.assertEqual(
            Path(module.__file__).resolve(),
            (ROOT / "benchmark" / "evaluate.py").resolve(),
        )
        self.assertEqual(module.__package__, "benchmark")

    def test_find_spec_reports_the_package_location(self):
        spec = importlib.util.find_spec("benchmark.evaluate")
        self.assertIsNotNone(spec)
        origin = Path(spec.origin).resolve()
        self.assertEqual(origin, (ROOT / "benchmark" / "evaluate.py").resolve())

    def test_validate_submission_uses_the_package_module(self):
        module = importlib.import_module("benchmark.validate_submission")
        self.assertEqual(
            Path(module.evaluate.__file__).resolve(),
            (ROOT / "benchmark" / "evaluate.py").resolve(),
        )

    def test_no_module_imports_a_bare_evaluate(self):
        for name in ("evaluate.py", "validate_submission.py"):
            source = (ROOT / "benchmark" / name).read_text(encoding="utf-8")
            for line in source.splitlines():
                stripped = line.strip()
                self.assertFalse(
                    stripped.startswith("import evaluate"),
                    f"{name} must not use a bare 'import evaluate': {stripped}",
                )


class HostileSysPathTests(unittest.TestCase):
    """A hostile entry on sys.path must not be able to shadow the package."""

    def run_isolated(self, tmp: Path, cwd: Path, hostile: Path | None) -> subprocess.CompletedProcess:
        hostile_dir = tmp / "hostile"
        hostile_dir.mkdir(exist_ok=True)
        (hostile_dir / "evaluate.py").write_text(HOSTILE, encoding="utf-8")

        env = dict(os.environ)
        pythonpath = [str(hostile_dir)]
        if hostile is not None:
            pythonpath.insert(0, str(hostile))
        env["PYTHONPATH"] = os.pathsep.join(pythonpath)

        return subprocess.run(  # nosec B603 - fixed argv, shell=False by default
            [
                sys.executable,
                "-m",
                "benchmark.validate_submission",
                "--root",
                "benchmark/results/community",
                "--allow-empty",
            ],
            cwd=str(cwd),
            env=env,
            capture_output=True,
            text=True,
        )

    def test_hostile_module_in_cwd_cannot_shadow(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            result = self.run_isolated(tmp, ROOT, None)
            self.assertNotIn("HIJACKED_BY_HOSTILE_MODULE", result.stdout + result.stderr)
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_hostile_module_in_a_separate_cwd_cannot_shadow(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            cwd = tmp / "elsewhere"
            cwd.mkdir()
            # cwd is deliberately outside the repository and contains a hostile
            # evaluate.py of its own
            (cwd / "evaluate.py").write_text(HOSTILE, encoding="utf-8")
            result = self.run_isolated(tmp, cwd, cwd)
            self.assertNotIn("HIJACKED_BY_HOSTILE_MODULE", result.stdout + result.stderr)

    def test_integrity_marker_rejects_an_incomplete_package(self):
        """A ``benchmark`` package missing its modules must refuse to initialise.

        A *complete* hostile substitution of the whole ``benchmark`` package is a
        property of Python's ``sys.path`` ordering (the working directory is
        searched before any repository code runs) and cannot be prevented from
        inside the package. What is testable, and what this asserts, is the
        integrity marker: a partial substitution raises rather than silently
        serving code the caller believes is the repository's own.
        """
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            cwd = Path(tmpdir) / "attacker"
            (cwd / "benchmark").mkdir(parents=True)
            (cwd / "benchmark" / "__init__.py").write_text(
                (ROOT / "benchmark" / "__init__.py").read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            env = dict(os.environ)
            env["PYTHONPATH"] = str(ROOT)
            result = subprocess.run(  # nosec B603 - fixed argv, shell=False by default
                [sys.executable, "-c", "import benchmark"],
                cwd=str(cwd),
                env=env,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("possibly substituted", result.stderr)

    def test_script_mode_still_works(self):
        result = subprocess.run(  # nosec B603 - fixed argv, shell=False by default
            [
                sys.executable,
                str(ROOT / "benchmark" / "validate_submission.py"),
                "--root",
                "benchmark/results/community",
                "--allow-empty",
            ],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
