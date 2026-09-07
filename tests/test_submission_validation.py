from __future__ import annotations
import importlib.util, json, sys, tempfile, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for name, path in (
    ("evaluate", ROOT / "benchmark" / "evaluate.py"),
    ("validate_submission", ROOT / "benchmark" / "validate_submission.py"),
):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)

evaluate = sys.modules["evaluate"]
validator = sys.modules["validate_submission"]


class SubmissionValidationTests(unittest.TestCase):
    def make_bundle(self, root: Path) -> Path:
        bundle = root / "provider-model-2026-09-07"
        bundle.mkdir()
        cases = [{"id": "c1", "domain": "math", "prompt": "1+1?", "accepted_answers": ["2"]}]
        baseline = [{"case_id": "c1", "answer": "2", "tokens": 10, "tool_calls": 0, "latency_ms": 100}]
        skill = [{"case_id": "c1", "answer": "2", "tokens": 12, "tool_calls": 0, "latency_ms": 110}]
        (bundle / "cases.jsonl").write_text(json.dumps(cases[0]) + "\n", encoding="utf-8")
        (bundle / "baseline.jsonl").write_text(json.dumps(baseline[0]) + "\n", encoding="utf-8")
        (bundle / "skill.jsonl").write_text(json.dumps(skill[0]) + "\n", encoding="utf-8")
        meta = {
            "provider": "example",
            "model": "model",
            "run_date": "2026-09-07",
            "skill_version": "0.3.0",
            "repetitions_per_case": 1,
            "failures_recorded": True,
            "baseline": {"instruction_config": "baseline", "sampling": {}, "tool_availability": [], "context_limit": 1000, "output_limit": 100},
            "skill": {"instruction_config": "SKILL.md", "sampling": {}, "tool_availability": [], "context_limit": 1000, "output_limit": 100},
        }
        (bundle / "metadata.json").write_text(json.dumps(meta), encoding="utf-8")
        payload = {"skill": evaluate.summarize(cases, skill), "baseline": evaluate.summarize(cases, baseline)}
        payload["comparison"] = evaluate.compare(payload["baseline"], payload["skill"])
        (bundle / "comparison.json").write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
        (bundle / "README.md").write_text("Reproducible test bundle.\n", encoding="utf-8")
        return bundle

    def test_valid_bundle(self):
        with tempfile.TemporaryDirectory() as tmp:
            validator.validate_bundle(self.make_bundle(Path(tmp)))

    def test_missing_artifact_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            bundle = self.make_bundle(Path(tmp))
            (bundle / "README.md").unlink()
            with self.assertRaises(ValueError):
                validator.validate_bundle(bundle)

    def test_tampered_comparison_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            bundle = self.make_bundle(Path(tmp))
            payload = json.loads((bundle / "comparison.json").read_text())
            payload["comparison"]["accuracy_delta"] = 99
            (bundle / "comparison.json").write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaises(ValueError):
                validator.validate_bundle(bundle)

    def test_unrecorded_failures_flag_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            bundle = self.make_bundle(Path(tmp))
            meta = json.loads((bundle / "metadata.json").read_text())
            meta["failures_recorded"] = False
            (bundle / "metadata.json").write_text(json.dumps(meta), encoding="utf-8")
            with self.assertRaises(ValueError):
                validator.validate_bundle(bundle)


if __name__ == "__main__":
    unittest.main()
