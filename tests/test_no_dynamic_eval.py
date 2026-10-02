"""Tests that no code path evaluates or deserialises untrusted input.

Benchmark bundles are pull-request content. The only deserialiser this project
may use for them is the JSON grammar: never ``eval``/``exec``/``compile``, never
``pickle``, ``marshal``, ``shelve``, ``dill``, ``yaml.load`` without a safe
loader, and never a format that can carry code.

The tests combine a static scan of the shipped sources with behavioural tests
that feed known-dangerous payloads through the real entry points and assert they
are handled as inert data.
"""

from __future__ import annotations

import ast
import importlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

evaluate = importlib.import_module("benchmark.evaluate")
validator = importlib.import_module("benchmark.validate_submission")

#: Directories whose Python sources ship to users or run in CI.
SCANNED_DIRS = ("benchmark", "reference", "quantum_reasoning_skill")

#: Bare names that must never be called in shipped code.
FORBIDDEN_CALLS = {
    "eval",
    "exec",
    "compile",
    "__import__",
    "system",
    "popen",
    "spawn",
    "fork",
    "execv",
    "execve",
    "execl",
    "check_output",
    "Popen",
    "run_module",
    "SourceFileLoader",
    "spec_from_file_location",
}

#: Attribute calls that must never appear, whatever the receiver.
FORBIDDEN_ATTRS = {
    "eval",
    "exec",
    "compile",
    "loads",
    "load",
    "load_module",
    "system",
    "popen",
    "spawn",
    "fork",
    "execv",
    "execve",
    "execl",
    "check_output",
    "run_module",
    "SourceFileLoader",
    "spec_from_file_location",
}

#: The single permitted deserialisation entry point.
ALLOWED_DESERIALISERS = {("json", "loads"), ("json", "load")}

#: Modules that must never be imported by shipped code.
FORBIDDEN_IMPORTS = {
    "pickle",
    "cPickle",
    "marshal",
    "shelve",
    "dill",
    "yaml",
    "subprocess",
    "ctypes",
    "code",
    "codeop",
    "pty",
    "socket",
    "requests",
    "urllib",
    "http",
    "importlib",
    "runpy",
    "ptyprocess",
    "multiprocessing",
}

PAYLOAD = "__import__('os').system('echo PWNED')"


def scan_source(path: Path) -> list[str]:
    """Return a list of policy violations for one Python source file."""
    offenders: list[str] = []
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id in FORBIDDEN_CALLS:
                offenders.append(f"line {node.lineno}: calls {func.id}()")
            elif isinstance(func, ast.Attribute) and func.attr in FORBIDDEN_ATTRS:
                receiver = func.value.id if isinstance(func.value, ast.Name) else None
                if (receiver, func.attr) not in ALLOWED_DESERIALISERS:
                    offender = f"line {node.lineno}: calls .{func.attr}()"
                    if receiver:
                        offender = f"line {node.lineno}: calls {receiver}.{func.attr}()"
                    offenders.append(offender)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] in FORBIDDEN_IMPORTS:
                    offenders.append(f"line {node.lineno}: imports {alias.name}")
        elif isinstance(node, ast.ImportFrom):
            if (node.module or "").split(".")[0] in FORBIDDEN_IMPORTS:
                offenders.append(f"line {node.lineno}: imports from {node.module}")
        elif isinstance(node, ast.Name) and node.id in {"eval", "exec", "__import__"}:
            offenders.append(f"line {node.lineno}: references {node.id}")
    return offenders


def shipped_sources() -> list[Path]:
    files: list[Path] = []
    for name in SCANNED_DIRS:
        directory = ROOT / name
        if directory.is_dir():
            files.extend(sorted(directory.rglob("*.py")))
    return files


class NoDynamicEvaluationTests(unittest.TestCase):
    def test_shipped_sources_exist(self):
        self.assertTrue(shipped_sources(), "no Python sources were found to scan")

    def test_no_forbidden_call_or_import(self):
        offenders: list[str] = []
        for path in shipped_sources():
            for violation in scan_source(path):
                offenders.append(f"{path.relative_to(ROOT)}: {violation}")
        self.assertEqual(
            offenders,
            [],
            "unsafe dynamic execution found:\n" + "\n".join(offenders),
        )

    def test_scanner_detects_a_planted_violation(self):
        """Negative control: the scanner must fail on code that does these things."""
        cases = {
            "eval_call": "eval('1+1')\n",
            "exec_call": "exec('x=1')\n",
            "compile_call": "compile('x', 'f', 'eval')\n",
            "dunder_import": "__import__('os')\n",
            "pickle_import": "import pickle\n",
            "subprocess_import": "from subprocess import run\n",
            "yaml_import": "import yaml\n",
            "importlib_import": "import importlib\n",
            "pickle_loads": "import json\nobj.loads('x')\n",
            "system_call": "import os\nos.system('id')\n",
            "popen_call": "import subprocess\nsubprocess.Popen('id')\n",
        }
        for label, source in cases.items():
            with self.subTest(case=label), tempfile.TemporaryDirectory() as tmp:
                planted = Path(tmp) / "planted.py"
                planted.write_text(source, encoding="utf-8")
                self.assertTrue(
                    scan_source(planted),
                    f"scanner failed to flag {label}: {source.strip()}",
                )

    def test_scanner_accepts_the_json_escape_hatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            clean = Path(tmp) / "clean.py"
            clean.write_text(
                "import json\nvalue = json.loads('{}')\n"
                "mapping = json.load(open('x'))\n"
                "text = open('y').read()\n",
                encoding="utf-8",
            )
            self.assertEqual(scan_source(clean), [])


class UntrustedPayloadTests(unittest.TestCase):
    """Dangerous-looking payloads must be handled as inert data."""

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

    def test_python_source_in_a_json_field_is_data_not_code(self):
        with tempfile.TemporaryDirectory() as tmp:
            bundle = self.make_bundle(Path(tmp) / "b")
            payload = json.loads((bundle / "comparison.json").read_text(encoding="utf-8"))
            payload["skill"]["model_note"] = PAYLOAD
            (bundle / "comparison.json").write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaises(ValueError):
                validator.validate_bundle(bundle)

    def test_non_json_input_is_rejected_not_executed(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "results.jsonl"
            target.write_text(PAYLOAD + "\n", encoding="utf-8")
            with self.assertRaises(ValueError) as ctx:
                evaluate.read_jsonl(target)
            self.assertIn("invalid JSON", str(ctx.exception))

    def test_json_array_row_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "results.jsonl"
            target.write_text('["not", "an", "object"]\n', encoding="utf-8")
            with self.assertRaises(ValueError):
                evaluate.read_jsonl(target)

    def test_pickle_style_payload_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "results.jsonl"
            target.write_bytes(b"\x80\x04\x95cos\nsystem\n")
            with self.assertRaises(ValueError):
                evaluate.read_jsonl(target)

    def test_boolean_is_not_accepted_as_a_numeric_metric(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "results.jsonl"
            row = {"case_id": "c1", "answer": "2", "tokens": True, "tool_calls": 0, "latency_ms": 1}
            target.write_text(json.dumps(row) + "\n", encoding="utf-8")
            rows = evaluate.read_jsonl(target)
            with self.assertRaises(ValueError):
                evaluate.validate_result(rows[0])

    def test_deeply_nested_json_does_not_execute(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "results.jsonl"
            target.write_text(json.dumps({"a": {"b": {"c": PAYLOAD}}}) + "\n", encoding="utf-8")
            rows = evaluate.read_jsonl(target)
            self.assertIn("a", rows[0])

    def test_extra_unknown_fields_are_ignored_not_executed(self):
        """Unknown keys must not be executed; they are simply carried as data."""
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "results.jsonl"
            row = {
                "case_id": "c1", "answer": "2", "tokens": 10, "tool_calls": 0,
                "latency_ms": 100, "__reduce__": [PAYLOAD], "note": "harmless",
            }
            target.write_text(json.dumps(row) + "\n", encoding="utf-8")
            rows = evaluate.read_jsonl(target)
            evaluate.validate_result(rows[0])
            summary = evaluate.summarize(
                [{"id": "c1", "domain": "math", "prompt": "1+1?", "accepted_answers": ["2"]}],
                rows,
            )
            self.assertEqual(summary["accuracy"], 1.0)

    def test_pickle_reduce_pairs_never_reach_a_loader(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "cases.jsonl"
            target.write_text(
                json.dumps({"id": "c1", "domain": "m", "prompt": "p",
                            "accepted_answers": ["a"], "__reduce__": ["os.system", ["id"]]}) + "\n",
                encoding="utf-8",
            )
            rows = evaluate.read_jsonl(target)
            evaluate.validate_case(rows[0])
            self.assertIn("__reduce__", rows[0])


if __name__ == "__main__":
    unittest.main()
