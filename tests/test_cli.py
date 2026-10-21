"""Behavioural tests for the packaged ``quantum-reasoning`` CLI.

``quantum_reasoning_skill/cli.py`` is production source under the full
statement-and-branch coverage gate, but its branches were previously only
exercised indirectly by packaging smoke tests. These tests pin the contract the
console script exposes to users: front-matter parsing and validation, version
and SKILL.md discovery, every output mode, and each documented exit code.
"""

from __future__ import annotations

import json
import runpy
import sys
import tempfile
import unittest
import unittest.mock as mock
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLI_PATH = ROOT / "quantum_reasoning_skill" / "cli.py"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quantum_reasoning_skill import cli  # noqa: E402

DESCRIPTION = "A valid description."
VALID_TEXT = (
    "---\n"
    "name: quantum-reasoning\n"
    f"description: {DESCRIPTION}\n"
    "---\n"
    + "\n".join(f"body line {number}" for number in range(20))
    + "\n"
)


def skill_text(
    *, name: str = "quantum-reasoning", body_lines: int = 20
) -> str:
    """Build a minimal skill document with a controllable name and body."""
    return (
        "---\n"
        f"name: {name}\n"
        f"description: {DESCRIPTION}\n"
        "---\n"
        + "\n".join(f"body line {number}" for number in range(body_lines))
        + "\n"
    )


def run_main(argv: list[str]) -> tuple[int, str, str]:
    """Invoke ``main`` and capture stdout, stderr and the exit code."""
    stdout = StringIO()
    stderr = StringIO()
    with redirect_stdout(stdout), redirect_stderr(stderr):
        code = cli.main(argv)
    return code, stdout.getvalue(), stderr.getvalue()


class CandidatePathTests(unittest.TestCase):
    def test_skill_candidates_are_package_checkout_and_cwd_deduplicated(self):
        expected_packaged = CLI_PATH.resolve().parent / "SKILL.md"
        expected_checkout = ROOT / "SKILL.md"

        # A checkout run from the repository root sees the same path from the
        # checkout and cwd probes; the duplicate must be dropped.
        with mock.patch.object(cli.Path, "cwd", return_value=ROOT):
            candidates = cli._candidate_skill_paths()

        self.assertEqual(candidates, [expected_packaged, expected_checkout])

    def test_version_candidates_are_package_then_checkout_root(self):
        package_dir = CLI_PATH.resolve().parent

        self.assertEqual(
            cli._candidate_version_paths(),
            [package_dir / "VERSION", package_dir.parent / "VERSION"],
        )


class LocateSkillFileTests(unittest.TestCase):
    def test_checkout_layout_finds_the_repository_skill_file(self):
        located = cli.locate_skill_file()

        self.assertIsNotNone(located)
        self.assertEqual(located.resolve(), (ROOT / "SKILL.md").resolve())

    def test_returns_none_when_no_candidate_exists(self):
        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp) / "SKILL.md"
            with mock.patch.object(
                cli, "_candidate_skill_paths", return_value=[missing]
            ):
                self.assertIsNone(cli.locate_skill_file())


class PackageVersionTests(unittest.TestCase):
    def test_reads_the_checkout_version_file(self):
        self.assertEqual(cli.package_version(), "1.2.0")

    def test_skips_missing_and_empty_candidates(self):
        with tempfile.TemporaryDirectory() as tmp:
            empty = Path(tmp) / "VERSION"
            empty.write_text("   \n", encoding="utf-8")
            with mock.patch.object(
                cli,
                "_candidate_version_paths",
                return_value=[Path(tmp) / "absent", empty],
            ):
                self.assertIsNone(cli.package_version())

    def test_strips_a_leading_v_prefix(self):
        with tempfile.TemporaryDirectory() as tmp:
            version_file = Path(tmp) / "VERSION"
            version_file.write_text("v9.8.7\n", encoding="utf-8")
            with mock.patch.object(
                cli, "_candidate_version_paths", return_value=[version_file]
            ):
                self.assertEqual(cli.package_version(), "9.8.7")


class ParseFrontMatterTests(unittest.TestCase):
    def test_parses_pairs_and_skips_comments_and_non_pairs(self):
        text = (
            "---\n"
            'name: "quantum-reasoning"\n'
            "description: 'A quoted description.'\n"
            "# comment: ignored\n"
            "not a pair\n"
            "---\n"
            "body\n"
        )

        fields, fence_end = cli.parse_front_matter(text)

        self.assertEqual(
            fields,
            {
                "name": "quantum-reasoning",
                "description": "A quoted description.",
            },
        )
        self.assertEqual(fence_end, 5)

    def test_rejects_empty_text_and_missing_opening_fence(self):
        with self.assertRaisesRegex(
            ValueError, "must start with a `---` front matter fence"
        ):
            cli.parse_front_matter("")
        with self.assertRaisesRegex(
            ValueError, "must start with a `---` front matter fence"
        ):
            cli.parse_front_matter("name: quantum-reasoning\n")

    def test_rejects_unclosed_front_matter(self):
        with self.assertRaisesRegex(ValueError, "front matter is not closed"):
            cli.parse_front_matter("---\nname: quantum-reasoning\n")


class ValidateSkillTextTests(unittest.TestCase):
    def test_accepts_a_complete_skill_document(self):
        report = cli.validate_skill_text(VALID_TEXT)

        self.assertEqual(
            report,
            {
                "name": "quantum-reasoning",
                "description": DESCRIPTION,
                "description_length": len(DESCRIPTION),
                "body_lines": 20,
                "valid": True,
                "problems": [],
            },
        )

    def test_reports_missing_fields_name_mismatch_and_short_body(self):
        report = cli.validate_skill_text("---\n---\n")

        self.assertFalse(report["valid"])
        self.assertEqual(report["name"], "")
        self.assertEqual(report["description"], "")
        self.assertEqual(report["description_length"], 0)
        self.assertEqual(report["body_lines"], 0)
        self.assertEqual(
            report["problems"],
            [
                "front matter must define a non-empty `name`",
                "front matter must define a non-empty `description`",
                "front matter `name` must be `quantum-reasoning`",
                "SKILL.md body is too short (0 lines, expected >= 20)",
            ],
        )

    def test_rejects_the_wrong_name_and_a_body_below_the_threshold(self):
        report = cli.validate_skill_text(skill_text(name="other", body_lines=19))

        self.assertFalse(report["valid"])
        self.assertEqual(report["name"], "other")
        self.assertEqual(report["body_lines"], 19)
        self.assertEqual(
            report["problems"],
            [
                "front matter `name` must be `quantum-reasoning`",
                "SKILL.md body is too short (19 lines, expected >= 20)",
            ],
        )


class MainTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)

    def write_skill(self, text: str = VALID_TEXT) -> Path:
        path = self.tmp / "SKILL.md"
        path.write_text(text, encoding="utf-8")
        return path

    def test_explicit_skill_file_json_report(self):
        path = self.write_skill()

        code, stdout, stderr = run_main(["--skill-file", str(path), "--json"])

        self.assertEqual(code, 0)
        self.assertEqual(stderr, "")
        report = json.loads(stdout)
        self.assertEqual(report["name"], "quantum-reasoning")
        self.assertEqual(report["description"], DESCRIPTION)
        self.assertEqual(report["body_lines"], 20)
        self.assertTrue(report["valid"])
        self.assertEqual(report["problems"], [])
        self.assertEqual(report["package_version"], "1.2.0")

    def test_explicit_skill_file_human_report(self):
        path = self.write_skill()

        code, stdout, stderr = run_main(["--skill-file", str(path)])

        self.assertEqual(code, 0)
        self.assertEqual(stderr, "")
        self.assertIn("skill:   quantum-reasoning", stdout)
        self.assertIn("status:  valid", stdout)
        self.assertIn(f"file:    {path}", stdout)
        self.assertIn("version: 1.2.0", stdout)
        self.assertIn("body:    20 lines", stdout)

    def test_human_report_of_an_invalid_skill_uses_placeholders(self):
        path = self.write_skill("---\n---\n")

        code, stdout, stderr = run_main(["--skill-file", str(path)])

        self.assertEqual(code, 0)
        self.assertEqual(stderr, "")
        self.assertIn("skill:   <missing name>", stdout)
        self.assertIn("status:  INVALID", stdout)
        self.assertIn("body:    0 lines", stdout)
        self.assertEqual(stdout.count("  - "), 4)

    def test_unknown_package_version_is_reported(self):
        path = self.write_skill()

        with mock.patch.object(cli, "package_version", return_value=None):
            code, stdout, stderr = run_main(["--skill-file", str(path)])

        self.assertEqual(code, 0)
        self.assertEqual(stderr, "")
        self.assertIn("version: unknown", stdout)

    def test_quiet_suppresses_output_for_valid_and_invalid_documents(self):
        valid = self.write_skill()

        code, stdout, stderr = run_main(["--skill-file", str(valid), "--quiet"])

        self.assertEqual((code, stdout, stderr), (0, "", ""))

        invalid = self.write_skill("---\n---\n")
        code, stdout, stderr = run_main(["--skill-file", str(invalid), "--quiet"])

        self.assertEqual((code, stdout, stderr), (0, "", ""))

    def test_validate_returns_success_for_a_valid_document(self):
        path = self.write_skill()

        code, stdout, stderr = run_main(
            ["--skill-file", str(path), "--validate", "--quiet"]
        )

        self.assertEqual((code, stdout, stderr), (0, "", ""))

    def test_validate_returns_failure_for_an_invalid_document(self):
        path = self.write_skill("---\n---\n")

        code, stdout, stderr = run_main(
            ["--skill-file", str(path), "--validate", "--quiet"]
        )

        self.assertEqual((code, stdout, stderr), (1, "", ""))

    def test_missing_explicit_skill_file_exits_two(self):
        missing = self.tmp / "absent-SKILL.md"

        code, stdout, stderr = run_main(["--skill-file", str(missing)])

        self.assertEqual(code, 2)
        self.assertEqual(stdout, "")
        self.assertIn("error: SKILL.md not found", stderr)
        self.assertIn("--skill-file", stderr)

    def test_missing_located_skill_file_exits_two(self):
        with mock.patch.object(cli, "locate_skill_file", return_value=None):
            code, stdout, stderr = run_main(["--json"])

        self.assertEqual(code, 2)
        self.assertEqual(stdout, "")
        self.assertIn("error: SKILL.md not found", stderr)

    def test_without_arguments_uses_the_checkout_skill_file(self):
        code, stdout, stderr = run_main(["--json"])

        self.assertEqual(code, 0)
        self.assertEqual(stderr, "")
        report = json.loads(stdout)
        self.assertEqual(report["name"], "quantum-reasoning")
        self.assertTrue(report["valid"])
        self.assertEqual(report["package_version"], "1.2.0")

    def test_os_error_reading_the_skill_file_exits_two(self):
        path = self.write_skill()

        with mock.patch.object(
            Path, "read_text", side_effect=OSError("permission denied")
        ):
            code, stdout, stderr = run_main(["--skill-file", str(path)])

        self.assertEqual(code, 2)
        self.assertEqual(stdout, "")
        self.assertIn(f"error: cannot read {path}", stderr)
        self.assertIn("permission denied", stderr)

    def test_invalid_utf8_skill_file_exits_two(self):
        path = self.tmp / "SKILL.md"
        path.write_bytes(b"---\nname: \xff\n---\n")

        code, stdout, stderr = run_main(["--skill-file", str(path)])

        self.assertEqual(code, 2)
        self.assertEqual(stdout, "")
        self.assertIn(f"error: cannot read {path}", stderr)

    def test_malformed_front_matter_exits_one(self):
        path = self.write_skill("no front matter here\n")

        code, stdout, stderr = run_main(["--skill-file", str(path)])

        self.assertEqual(code, 1)
        self.assertEqual(stdout, "")
        self.assertIn(f"error: {path}", stderr)
        self.assertIn("must start with a `---` front matter fence", stderr)

    def test_module_entry_point_exits_with_main_status(self):
        argv = [
            "quantum-reasoning",
            "--skill-file",
            str(ROOT / "SKILL.md"),
            "--validate",
            "--quiet",
        ]

        with mock.patch.object(sys, "argv", argv), self.assertRaises(
            SystemExit
        ) as raised:
            runpy.run_path(str(CLI_PATH), run_name="__main__")

        self.assertEqual(raised.exception.code, 0)


if __name__ == "__main__":
    unittest.main()
