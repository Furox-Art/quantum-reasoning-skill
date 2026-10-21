"""Import and wheel-boundary contracts for the installed console script.

Two packaging regressions are pinned here:

* the console script is declared as ``quantum_reasoning_skill.cli:main``, but the
  module only existed inside a built wheel, so importing it from a checkout (and
  any source-based tooling) failed;
* hatchling's ``only-include`` pulled the repository's top-level asset
  directories (``benchmark``, ``reference``, ``docs``, ``examples``) into the
  wheel, where they shadow unrelated import names after installation. Those
  directories now live at their canonical locations inside
  ``quantum_reasoning_skill/`` (or remain repository-only assets for docs and
  examples), and the wheel must not contain any other top-level directory.

The wheel is built into a temporary directory so the checkout and its committed
``dist/`` directory are never modified.
"""

from __future__ import annotations

import importlib
import importlib.util
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class CliImportContractTests(unittest.TestCase):
    def test_cli_module_imports_and_exposes_callable_main(self):
        module = importlib.import_module("quantum_reasoning_skill.cli")

        self.assertTrue(callable(module.main))


class WheelBoundaryTests(unittest.TestCase):
    def test_wheel_top_level_names_are_only_package_and_dist_info(self):
        with tempfile.TemporaryDirectory() as tmp:
            outdir = Path(tmp)
            self._build_wheel(outdir)
            wheels = sorted(outdir.glob("*.whl"))
            self.assertEqual(
                len(wheels), 1, f"expected exactly one wheel, found {wheels!r}"
            )
            with zipfile.ZipFile(wheels[0]) as archive:
                top_level = {
                    name.split("/", 1)[0] for name in archive.namelist() if name
                }

        dist_info = {name for name in top_level if name.endswith(".dist-info")}
        self.assertEqual(
            len(dist_info), 1, f"expected one dist-info directory, found {dist_info!r}"
        )
        self.assertEqual(
            top_level,
            {"quantum_reasoning_skill", *dist_info},
            "wheel exposes unexpected top-level entries: "
            f"{sorted(top_level - {'quantum_reasoning_skill'} - dist_info)!r}",
        )

    @staticmethod
    def _build_wheel(outdir: Path) -> None:
        """Build a wheel with ``build`` when available, otherwise with pip.

        ``build`` is a dev-only dependency, so the behavioural test jobs may not
        have it. pip is always present and performs the same PEP 517 build.
        """
        if importlib.util.find_spec("build") is not None:
            command = [
                sys.executable,
                "-m",
                "build",
                "--wheel",
                "--no-isolation",
                "--outdir",
                str(outdir),
            ]
            try:
                subprocess.run(
                    command, cwd=ROOT, check=True, capture_output=True, text=True
                )
            except subprocess.CalledProcessError:
                # ``build`` without hatchling cannot use --no-isolation; retry
                # below with pip's isolated build rather than masking the error.
                pass
            else:
                return
        command = [
            sys.executable,
            "-m",
            "pip",
            "wheel",
            "--no-deps",
            "--wheel-dir",
            str(outdir),
            str(ROOT),
        ]
        try:
            subprocess.run(
                command, cwd=ROOT, check=True, capture_output=True, text=True
            )
        except subprocess.CalledProcessError as exc:
            raise AssertionError(
                "building the wheel failed:\n"
                f"stdout:\n{exc.stdout}\nstderr:\n{exc.stderr}"
            ) from None
