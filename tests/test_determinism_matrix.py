from __future__ import annotations

import importlib.util
import json
import platform
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
ENGINE = REPO_ROOT / "scripts" / "determinism_matrix.py"
WORKLOAD = REPO_ROOT / "scripts" / "determinism_workload.py"


def run_engine(*args: object) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(ENGINE), *(str(arg) for arg in args)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=300,
        check=False,
    )


def load_manifest(path: Path) -> dict[str, Any]:
    data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return data


def _engine() -> Any:
    spec = importlib.util.spec_from_file_location("determinism_matrix_under_test", ENGINE)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class DeterminismMatrixTests(unittest.TestCase):
    def run_with_marker(
        self, root: Path, marker: str, name: str, *extra: object
    ) -> tuple[Path, Path]:
        workload = root / f"{name}_workload.py"
        workload.write_text(
            "from pathlib import Path\n"
            "marker = Path(__file__).with_name('marker.txt')\n"
            "print(marker.read_text(encoding='utf-8'))\n",
            encoding="utf-8",
        )
        (root / "marker.txt").write_text(marker, encoding="utf-8")
        out = root / f"{name}.json"
        completed = run_engine(
            "run",
            "--workload",
            workload,
            "--out",
            out,
            "--seeds",
            "0",
            "--threads",
            1,
            *extra,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        return workload, out

    def test_matrix_output_is_identical_across_seeds_and_threads(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "manifest.json"
            completed = run_engine(
                "run",
                "--workload",
                WORKLOAD,
                "--out",
                out,
                "--seeds",
                "0",
                "12345",
                "--threads",
                1,
                2,
                "--gate",
                "within-host",
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            data = load_manifest(out)
            self.assertEqual(data["schema_version"], 1)
            self.assertIs(data["summary"]["identical"], True)
            self.assertEqual(data["summary"]["run_count"], 4)
            self.assertEqual(
                data["gate"],
                {
                    "mode": "within-host",
                    "passed": True,
                    "probe_failures": [],
                    "inert_axes": [],
                },
            )
            self.assertTrue(all(run["exit_code"] == 0 for run in data["runs"]))
            self.assertEqual(
                [item["path"] for item in data["runs"][0]["artifacts"]],
                ["payload.json"],
            )
            self.assertGreater(data["runs"][0]["artifacts"][0]["bytes"], 0)

    def test_stdout_newlines_are_normalized_before_hashing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            crlf = root / "crlf.py"
            crlf.write_text(
                "import sys\nsys.stdout.buffer.write(b'a\\r\\nb\\n')\n",
                encoding="utf-8",
            )
            lf = root / "lf.py"
            lf.write_text(
                "import sys\nsys.stdout.buffer.write(b'a\\nb\\n')\n", encoding="utf-8"
            )
            crlf_out = root / "crlf.json"
            lf_out = root / "lf.json"
            for workload, out in ((crlf, crlf_out), (lf, lf_out)):
                completed = run_engine(
                    "run", "--workload", workload, "--out", out, "--seeds", "0", "--threads", 1
                )
                self.assertEqual(completed.returncode, 0, completed.stderr)
            crlf_run = load_manifest(crlf_out)["runs"][0]
            lf_run = load_manifest(lf_out)["runs"][0]
            self.assertEqual(crlf_run["stdout_sha256"], lf_run["stdout_sha256"])
            self.assertNotEqual(
                crlf_run["stdout_raw_sha256"], lf_run["stdout_raw_sha256"]
            )

    def test_matrix_records_the_requested_thread_environment(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "probe.json"
            completed = run_engine(
                "run",
                "--workload",
                WORKLOAD,
                "--out",
                out,
                "--seeds",
                "0",
                "--threads",
                1,
                "--gate",
                "within-host",
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            probe = load_manifest(out)["thread_probe"]["1"]
            self.assertEqual(probe["requested_threads"], 1)
            self.assertIs(probe["environment_matches_request"], True)
            self.assertEqual(probe["environment"]["OMP_NUM_THREADS"], "1")

    def test_matrix_gate_detects_a_hash_order_leak(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            leaky = root / "leaky.py"
            leaky.write_text(
                "import json\n"
                "print(json.dumps(list({'alpha', 'beta', 'gamma', 'delta', 'epsilon'})))\n",
                encoding="utf-8",
            )
            out = root / "leaky.json"
            completed = run_engine(
                "run",
                "--workload",
                leaky,
                "--out",
                out,
                "--seeds",
                "0",
                "12345",
                "--threads",
                1,
                "--gate",
                "within-host",
            )
            self.assertEqual(completed.returncode, 3)
            self.assertIs(load_manifest(out)["summary"]["identical"], False)

    def test_matrix_reports_a_workload_error_separately(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            broken = root / "broken.py"
            broken.write_text("raise RuntimeError('boom')\n", encoding="utf-8")
            out = root / "broken.json"
            completed = run_engine(
                "run", "--workload", broken, "--out", out, "--seeds", "0", "--threads", 1
            )
            self.assertEqual(completed.returncode, 4)
            self.assertEqual(load_manifest(out)["runs"][0]["exit_code"], 1)

    def test_matrix_records_locale_and_timezone_variants(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            probe = root / "environment_report.py"
            probe.write_text(
                "import json\nimport os\n"
                "keys = ('LC_ALL', 'LANG', 'LANGUAGE', 'TZ')\n"
                "print(json.dumps({key: os.environ.get(key) for key in keys}))\n",
                encoding="utf-8",
            )
            out = root / "environment.json"
            completed = run_engine(
                "run",
                "--workload",
                probe,
                "--out",
                out,
                "--seeds",
                "0",
                "--threads",
                1,
                "--locales",
                "inherit",
                "C",
                "--timezones",
                "UTC",
                "Europe/Istanbul",
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            data = load_manifest(out)
            self.assertEqual(data["variants"]["locales"], ["inherit", "C"])
            self.assertEqual(
                data["variants"]["timezones"], ["UTC", "Europe/Istanbul"]
            )
            self.assertEqual(data["summary"]["run_count"], 4)
            self.assertIs(data["summary"]["identical"], False)
            runs = {(run["locale"], run["timezone"]): run for run in data["runs"]}
            self.assertNotEqual(
                runs[("C", "UTC")]["stdout_sha256"],
                runs[("inherit", "UTC")]["stdout_sha256"],
            )
            report = data["environment_probe"]["locale=C|tz=UTC"]
            self.assertEqual(report["requested_locale"], "C")
            self.assertEqual(report["requested_timezone"], "UTC")
            self.assertEqual(report["environment"]["LC_ALL"], "C")
            self.assertEqual(report["environment"]["TZ"], "UTC")

    def test_axis_effectiveness_separates_inert_and_applied_axes(self) -> None:
        def probe(locale: str, tzname: list[str], offset: int, altzone: int) -> dict[str, Any]:
            return {
                "locale": locale,
                "tzname": tzname,
                "timezone": offset,
                "altzone": altzone,
            }

        probes = {
            "locale=inherit|tz=UTC": probe("C.UTF-8", ["UTC", "UTC"], 0, 0),
            "locale=C|tz=UTC": probe("C", ["UTC", "UTC"], 0, 0),
            "locale=inherit|tz=Europe/Istanbul": probe(
                "C.UTF-8", ["+03", "+03"], -10800, -14400
            ),
            "locale=C|tz=Europe/Istanbul": probe(
                "C", ["+03", "+03"], -10800, -14400
            ),
        }
        engine = _engine()
        axes = engine.axis_effectiveness(
            probes, ["inherit", "C"], ["UTC", "Europe/Istanbul"]
        )
        self.assertEqual(
            axes["locale"], {"requested": ["inherit", "C"], "applied": True}
        )
        self.assertEqual(
            axes["timezone"],
            {"requested": ["UTC", "Europe/Istanbul"], "applied": True},
        )

        inert_locale = {
            key: {**value, "locale": "C"} for key, value in probes.items()
        }
        axes = engine.axis_effectiveness(
            inert_locale, ["inherit", "C"], ["UTC", "Europe/Istanbul"]
        )
        self.assertIs(axes["locale"]["applied"], False)
        self.assertIn("note", axes["locale"])
        self.assertIs(axes["timezone"]["applied"], True)

        inert_timezone = {
            key: {**value, "tzname": ["UTC", "UTC"], "timezone": 0, "altzone": 0}
            for key, value in probes.items()
        }
        axes = engine.axis_effectiveness(
            inert_timezone, ["inherit", "C"], ["UTC", "Europe/Istanbul"]
        )
        self.assertIs(axes["timezone"]["applied"], False)
        self.assertIn("note", axes["timezone"])
        self.assertIs(axes["locale"]["applied"], True)

        single = engine.axis_effectiveness(probes, ["inherit"], ["UTC"])
        self.assertIs(single["locale"]["applied"], True)
        self.assertIs(single["timezone"]["applied"], True)

    def test_axes_reflect_the_effective_host_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workload = root / "axis_workload.py"
            workload.write_text("print('constant')\n", encoding="utf-8")
            completed = run_engine(
                "run",
                "--workload",
                workload,
                "--out",
                root / "axes.json",
                "--seeds",
                "0",
                "--threads",
                1,
                "--locales",
                "inherit",
                "C",
                "--timezones",
                "UTC",
                "Europe/Istanbul",
                "--gate",
                "within-host",
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            data = load_manifest(root / "axes.json")
            supported = platform.system() != "Windows"
            self.assertIs(data["axes"]["locale"]["applied"], supported)
            self.assertIs(data["axes"]["timezone"]["applied"], supported)
            self.assertEqual(
                data["gate"]["inert_axes"],
                [] if supported else ["locale", "timezone"],
            )
            self.assertIs(data["gate"]["passed"], True)

    def test_gate_fails_when_a_supported_axis_is_inert(self) -> None:
        engine = _engine()
        engine.axis_support = lambda: {"locale": True, "timezone": True}
        engine.probe_environment = lambda locale, timezone, timeout: {
            "requested_locale": locale,
            "requested_timezone": timezone,
            "environment_matches_request": True,
            "environment": {
                "LC_ALL": None,
                "LANG": None,
                "LANGUAGE": None,
                "TZ": None,
            },
            "locale": "C",
            "tzname": ["UTC", "UTC"],
            "timezone": 0,
            "altzone": 0,
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workload = root / "constant.py"
            workload.write_text("print('constant')\n", encoding="utf-8")
            exit_code = engine.main(
                [
                    "run",
                    "--workload",
                    str(workload),
                    "--out",
                    str(root / "axes.json"),
                    "--seeds",
                    "0",
                    "--threads",
                    "1",
                    "--locales",
                    "inherit",
                    "C",
                    "--timezones",
                    "UTC",
                    "Europe/Istanbul",
                    "--gate",
                    "within-host",
                ]
            )
            self.assertEqual(exit_code, 4)
            data = load_manifest(root / "axes.json")
            self.assertIs(data["gate"]["passed"], False)
            self.assertEqual(
                data["gate"]["inert_axes"], ["locale", "timezone"]
            )

    def test_compare_gate_detects_stdout_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _, baseline = self.run_with_marker(root, "one\n", "baseline")
            (root / "marker.txt").write_text("two\n", encoding="utf-8")
            out = root / "candidate.json"
            completed = run_engine(
                "run",
                "--workload",
                root / "baseline_workload.py",
                "--out",
                out,
                "--seeds",
                "0",
                "--threads",
                1,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            compared = run_engine("compare", baseline, out, "--gate")
            self.assertEqual(compared.returncode, 3)
            report = json.loads(compared.stdout)
            self.assertIs(report["comparable"], True)
            self.assertIs(report["identical"], False)
            self.assertIs(report["mismatches"][0]["stdout_mismatch"], True)
            self.assertIs(report["mismatches"][0]["artifacts_mismatch"], False)

    def test_compare_gate_detects_artifact_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workload = root / "artifact_workload.py"
            workload.write_text(
                "import os\n"
                "from pathlib import Path\n"
                "marker = Path(__file__).with_name('marker.txt').read_text(encoding='utf-8')\n"
                "out = Path(os.environ['DETERMINISM_ARTIFACT_DIR'], 'payload.txt')\n"
                "out.write_text(marker, encoding='utf-8', newline='\\n')\n"
                "print('constant')\n",
                encoding="utf-8",
            )
            (root / "marker.txt").write_text("one\n", encoding="utf-8")
            baseline = root / "baseline.json"
            candidate = root / "candidate.json"
            first = run_engine(
                "run", "--workload", workload, "--out", baseline, "--seeds", "0", "--threads", 1
            )
            self.assertEqual(first.returncode, 0, first.stderr)
            (root / "marker.txt").write_text("two\n", encoding="utf-8")
            second = run_engine(
                "run", "--workload", workload, "--out", candidate, "--seeds", "0", "--threads", 1
            )
            self.assertEqual(second.returncode, 0, second.stderr)
            compared = run_engine("compare", baseline, candidate, "--gate")
            self.assertEqual(compared.returncode, 3)
            report = json.loads(compared.stdout)
            self.assertIs(report["identical"], False)
            self.assertIs(report["mismatches"][0]["stdout_mismatch"], False)
            self.assertIs(report["mismatches"][0]["artifacts_mismatch"], True)
            self.assertEqual(report["mismatches"][0]["artifact_paths"], ["payload.txt"])

    def test_compare_normalizes_crlf_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workload = root / "newline_workload.py"
            workload.write_text(
                "import os\n"
                "from pathlib import Path\n"
                "mode = Path(__file__).with_name('mode.txt').read_text(encoding='utf-8').strip()\n"
                "newline = b'\\r\\n' if mode == 'crlf' else b'\\n'\n"
                "out = Path(os.environ['DETERMINISM_ARTIFACT_DIR'], 'payload.txt')\n"
                "out.write_bytes(b'a' + newline + b'b' + newline)\n"
                "print('constant')\n",
                encoding="utf-8",
            )
            (root / "mode.txt").write_text("crlf\n", encoding="utf-8")
            baseline = root / "baseline.json"
            candidate = root / "candidate.json"
            first = run_engine(
                "run", "--workload", workload, "--out", baseline, "--seeds", "0", "--threads", 1
            )
            self.assertEqual(first.returncode, 0, first.stderr)
            (root / "mode.txt").write_text("lf\n", encoding="utf-8")
            second = run_engine(
                "run", "--workload", workload, "--out", candidate, "--seeds", "0", "--threads", 1
            )
            self.assertEqual(second.returncode, 0, second.stderr)
            baseline_artifact = load_manifest(baseline)["runs"][0]["artifacts"][0]
            candidate_artifact = load_manifest(candidate)["runs"][0]["artifacts"][0]
            self.assertNotEqual(
                baseline_artifact["raw_sha256"], candidate_artifact["raw_sha256"]
            )
            self.assertEqual(
                baseline_artifact["sha256"], candidate_artifact["sha256"]
            )
            compared = run_engine("compare", baseline, candidate, "--gate")
            self.assertEqual(compared.returncode, 0, compared.stderr)
            self.assertIs(json.loads(compared.stdout)["identical"], True)

    def test_compare_gate_detects_missing_variants(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workload = root / "constant.py"
            workload.write_text("print('constant')\n", encoding="utf-8")
            baseline = root / "baseline.json"
            candidate = root / "candidate.json"
            first = run_engine(
                "run",
                "--workload",
                workload,
                "--out",
                baseline,
                "--seeds",
                "0",
                "--threads",
                1,
                "--locales",
                "inherit",
                "C",
            )
            self.assertEqual(first.returncode, 0, first.stderr)
            second = run_engine(
                "run",
                "--workload",
                workload,
                "--out",
                candidate,
                "--seeds",
                "0",
                "--threads",
                1,
                "--locales",
                "inherit",
            )
            self.assertEqual(second.returncode, 0, second.stderr)
            compared = run_engine("compare", baseline, candidate, "--gate")
            self.assertEqual(compared.returncode, 3)
            report = json.loads(compared.stdout)
            self.assertIs(report["identical"], False)
            self.assertEqual(report["mismatches"], [])
            self.assertTrue(report["baseline_only_variants"])

    def test_compare_rejects_schema_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workload = root / "constant.py"
            workload.write_text("print('constant')\n", encoding="utf-8")
            baseline = root / "baseline.json"
            candidate = root / "candidate.json"
            for out in (baseline, candidate):
                completed = run_engine(
                    "run", "--workload", workload, "--out", out, "--seeds", "0", "--threads", 1
                )
                self.assertEqual(completed.returncode, 0, completed.stderr)
            data = load_manifest(candidate)
            data["schema_version"] = 999
            candidate.write_text(json.dumps(data), encoding="utf-8")
            compared = run_engine("compare", baseline, candidate, "--gate")
            self.assertEqual(compared.returncode, 2)
            report = json.loads(compared.stdout)
            self.assertIs(report["comparable"], False)
            self.assertTrue(
                any("schema_version" in error for error in report["errors"])
            )

    def test_compare_rejects_failed_runs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            broken = root / "broken.py"
            broken.write_text("raise RuntimeError('boom')\n", encoding="utf-8")
            baseline = root / "baseline.json"
            candidate = root / "candidate.json"
            for out in (baseline, candidate):
                completed = run_engine(
                    "run", "--workload", broken, "--out", out, "--seeds", "0", "--threads", 1
                )
                self.assertEqual(completed.returncode, 4)
            compared = run_engine("compare", baseline, candidate, "--gate")
            self.assertEqual(compared.returncode, 2)
            report = json.loads(compared.stdout)
            self.assertIs(report["comparable"], False)
            self.assertTrue(any("exited 1" in error for error in report["errors"]))


if __name__ == "__main__":
    unittest.main()
