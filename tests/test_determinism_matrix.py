"""End-to-end checks for the determinism matrix engine and its falsification workload."""

from __future__ import annotations

import json
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


class DeterminismMatrixTests(unittest.TestCase):
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
            self.assertIs(data["summary"]["identical"], True)
            self.assertEqual(data["summary"]["run_count"], 4)
            self.assertEqual(data["gate"], {"mode": "within-host", "passed": True})
            self.assertTrue(all(run["exit_code"] == 0 for run in data["runs"]))
            self.assertEqual(
                [item["path"] for item in data["runs"][0]["artifacts"]], ["payload.json"]
            )
            self.assertGreater(data["runs"][0]["artifacts"][0]["bytes"], 0)

    def test_stdout_newlines_are_normalized_before_hashing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            crlf = root / "crlf.py"
            crlf.write_text(
                "import sys\nsys.stdout.buffer.write(b'a\\r\\nb\\n')\n", encoding="utf-8"
            )
            lf = root / "lf.py"
            lf.write_text("import sys\nsys.stdout.buffer.write(b'a\\nb\\n')\n", encoding="utf-8")
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
            self.assertNotEqual(crlf_run["stdout_raw_sha256"], lf_run["stdout_raw_sha256"])

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


if __name__ == "__main__":
    unittest.main()
