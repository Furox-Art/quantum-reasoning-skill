"""Traversal-guard tests for the benchmark tooling.

Community benchmark bundles arrive through pull requests, so every path the
validator touches is untrusted. The guards under test live in
:mod:`benchmark.paths` and are applied by :mod:`benchmark.validate_submission`
and :mod:`benchmark.evaluate`.
"""

from __future__ import annotations

import importlib
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

paths = importlib.import_module("benchmark.paths")
evaluate = importlib.import_module("benchmark.evaluate")
validator = importlib.import_module("benchmark.validate_submission")

PathBoundaryError = paths.PathBoundaryError


class ResolveWithinTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.base = Path(self._tmp.name) / "anchor"
        self.base.mkdir()
        (self.base / "inside.txt").write_text("ok", encoding="utf-8")

    def tearDown(self):
        self._tmp.cleanup()

    def test_accepts_a_plain_child(self):
        resolved = paths.resolve_within(self.base, "inside.txt")
        self.assertEqual(resolved, (self.base / "inside.txt").resolve())

    def test_accepts_the_base_itself(self):
        self.assertEqual(paths.resolve_within(self.base, "."), self.base.resolve())

    def test_rejects_parent_traversal(self):
        with self.assertRaises(PathBoundaryError):
            paths.resolve_within(self.base, "../outside.txt")

    def test_rejects_deep_parent_traversal(self):
        with self.assertRaises(PathBoundaryError):
            paths.resolve_within(self.base, "a/../../outside.txt")

    def test_rejects_absolute_path_outside_base(self):
        with tempfile.TemporaryDirectory() as other:
            with self.assertRaises(PathBoundaryError):
                paths.resolve_within(self.base, Path(other) / "evil.txt")

    def test_rejects_sibling_with_shared_prefix(self):
        """``anchor-evil`` must not pass as being inside ``anchor``."""
        evil = self.base.parent / f"{self.base.name}-evil"
        evil.mkdir()
        payload = evil / "payload.txt"
        payload.write_text("nope", encoding="utf-8")
        try:
            with self.assertRaises(PathBoundaryError):
                paths.resolve_within(self.base, evil / "payload.txt")
        finally:
            payload.unlink()
            evil.rmdir()

    @unittest.skipUnless(hasattr(os, "symlink"), "symlinks unavailable")
    def test_rejects_symlink_pointing_outside(self):
        with tempfile.TemporaryDirectory() as other:
            target = Path(other) / "secret.txt"
            target.write_text("SECRET", encoding="utf-8")
            link = self.base / "link.txt"
            try:
                os.symlink(target, link)
            except (OSError, NotImplementedError):
                self.skipTest("symlink creation not permitted on this host")
            with self.assertRaises(PathBoundaryError):
                paths.resolve_within(self.base, "link.txt")

    @unittest.skipUnless(hasattr(os, "symlink"), "symlinks unavailable")
    def test_allows_symlink_that_stays_inside(self):
        inside = self.base / "real.txt"
        inside.write_text("fine", encoding="utf-8")
        link = self.base / "alias.txt"
        try:
            os.symlink(inside, link)
        except (OSError, NotImplementedError):
            self.skipTest("symlink creation not permitted on this host")
        self.assertEqual(paths.resolve_within(self.base, "alias.txt"), inside.resolve())

    def test_require_within_raises_value_error_with_context(self):
        with self.assertRaises(ValueError) as ctx:
            paths.require_within(self.base, "../outside.txt", what="bundle member")
        self.assertIn("bundle member", str(ctx.exception))


class SafeBundleMemberTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.bundle = Path(self._tmp.name) / "bundle"
        self.bundle.mkdir()

    def tearDown(self):
        self._tmp.cleanup()

    def test_rejects_dotdot(self):
        with self.assertRaises(ValueError):
            paths.safe_bundle_member(self.bundle, "../metadata.json")

    def test_rejects_absolute_name(self):
        with self.assertRaises(ValueError):
            paths.safe_bundle_member(self.bundle, "/etc/passwd")

    def test_rejects_empty_name(self):
        with self.assertRaises(ValueError):
            paths.safe_bundle_member(self.bundle, "")

    def test_accepts_plain_name(self):
        self.assertEqual(
            paths.safe_bundle_member(self.bundle, "metadata.json"),
            (self.bundle / "metadata.json").resolve(),
        )


class ReadJsonlBoundaryTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.base = Path(self._tmp.name) / "base"
        self.base.mkdir()

    def tearDown(self):
        self._tmp.cleanup()

    def test_rejects_input_outside_the_declared_base(self):
        with tempfile.TemporaryDirectory() as other:
            outside = Path(other) / "results.jsonl"
            outside.write_text("{}\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                evaluate.read_jsonl(outside, base=self.base)

    def test_rejects_traversal_in_the_input_name(self):
        with self.assertRaises(ValueError):
            evaluate.read_jsonl(Path("../escape.jsonl"), base=self.base)

    def test_accepts_a_file_inside_the_base(self):
        target = self.base / "results.jsonl"
        target.write_text('{"case_id": "c1"}\n', encoding="utf-8")
        rows = evaluate.read_jsonl(target, base=self.base)
        self.assertEqual(rows, [{"case_id": "c1"}])

    def test_enforces_the_size_bound(self):
        target = self.base / "big.jsonl"
        target.write_text("x" * 4096, encoding="utf-8")
        with self.assertRaises(evaluate.UnsafeJsonError):
            evaluate.read_jsonl(target, base=self.base, max_bytes=16)


class ValidateBundleBoundaryTests(unittest.TestCase):
    """End-to-end: a bundle whose members point outside itself must be rejected."""

    def make_bundle(self, bundle: Path) -> Path:
        bundle.mkdir(parents=True)
        cases = [{"id": "c1", "domain": "math", "prompt": "1+1?", "accepted_answers": ["2"]}]
        baseline = [{"case_id": "c1", "answer": "2", "tokens": 10, "tool_calls": 0, "latency_ms": 100}]
        skill = [{"case_id": "c1", "answer": "2", "tokens": 12, "tool_calls": 0, "latency_ms": 110}]
        (bundle / "cases.jsonl").write_text(json.dumps(cases[0]) + "\n", encoding="utf-8")
        (bundle / "baseline.jsonl").write_text(json.dumps(baseline[0]) + "\n", encoding="utf-8")
        (bundle / "skill.jsonl").write_text(json.dumps(skill[0]) + "\n", encoding="utf-8")
        meta = {
            "provider": "example", "model": "model", "run_date": "2026-09-07",
            "skill_version": "0.3.0", "repetitions_per_case": 1, "failures_recorded": True,
            "baseline": {"instruction_config": "baseline", "sampling": {}, "tool_availability": [], "context_limit": 1000, "output_limit": 100},
            "skill": {"instruction_config": "SKILL.md", "sampling": {}, "tool_availability": [], "context_limit": 1000, "output_limit": 100},
        }
        (bundle / "metadata.json").write_text(json.dumps(meta), encoding="utf-8")
        payload = {"skill": evaluate.summarize(cases, skill), "baseline": evaluate.summarize(cases, baseline)}
        payload["comparison"] = evaluate.compare(payload["baseline"], payload["skill"])
        (bundle / "comparison.json").write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
        (bundle / "README.md").write_text("Reproducible test bundle.\n", encoding="utf-8")
        return bundle

    def test_valid_bundle_still_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            validator.validate_bundle(self.make_bundle(Path(tmp) / "b"))

    @unittest.skipUnless(hasattr(os, "symlink"), "symlinks unavailable")
    def test_symlinked_member_escaping_the_bundle_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            bundle = self.make_bundle(tmp / "b")
            outside = tmp / "outside.json"
            outside.write_text("{}", encoding="utf-8")
            # replace the real member with a link that points out of the bundle
            (bundle / "metadata.json").unlink()
            try:
                os.symlink(outside, bundle / "metadata.json")
            except (OSError, NotImplementedError):
                self.skipTest("symlink creation not permitted on this host")
            with self.assertRaises(ValueError) as ctx:
                validator.validate_bundle(bundle)
            self.assertIn("must stay inside", str(ctx.exception))

    @unittest.skipUnless(hasattr(os, "symlink"), "symlinks unavailable")
    def test_symlinked_bundle_directory_is_resolved(self):
        """A bundle reached through a symlink is validated against its real path."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            real = self.make_bundle(tmp / "real-bundle")
            link_parent = tmp / "linked"
            link_parent.mkdir()
            link = link_parent / "alias"
            try:
                os.symlink(real, link, target_is_directory=True)
            except (OSError, NotImplementedError):
                self.skipTest("symlink creation not permitted on this host")
            validator.validate_bundle(link)


class EvaluatorOutputBoundaryTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.base = Path(self._tmp.name) / "data"
        self.base.mkdir()
        self.cases = self.base / "cases.jsonl"
        self.cases.write_text(
            json.dumps({"id": "c1", "domain": "math", "prompt": "1+1?", "accepted_answers": ["2"]}) + "\n",
            encoding="utf-8",
        )
        self.skill = self.base / "skill.jsonl"
        self.skill.write_text(
            json.dumps({"case_id": "c1", "answer": "2", "tokens": 10, "tool_calls": 0, "latency_ms": 100}) + "\n",
            encoding="utf-8",
        )

    def tearDown(self):
        self._tmp.cleanup()

    def test_output_inside_the_cases_dir_is_written(self):
        target = self.base / "summary.json"
        code = evaluate.main([
            "--cases", str(self.cases), "--skill", str(self.skill),
            "--cases-dir", str(self.base), "--output", str(target),
        ])
        self.assertEqual(code, 0)
        self.assertTrue(target.is_file())

    def test_output_outside_the_cases_dir_is_rejected(self):
        with tempfile.TemporaryDirectory() as other:
            target = Path(other) / "escaped.json"
            with self.assertRaises(ValueError):
                evaluate.main([
                    "--cases", str(self.cases), "--skill", str(self.skill),
                    "--cases-dir", str(self.base), "--output", str(target),
                ])
            self.assertFalse(target.exists())

    def test_output_traversal_is_rejected(self):
        with self.assertRaises(ValueError):
            evaluate.main([
                "--cases", str(self.cases), "--skill", str(self.skill),
                "--cases-dir", str(self.base), "--output", "../escaped.json",
            ])


if __name__ == "__main__":
    unittest.main()
