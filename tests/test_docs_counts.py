"""Documentation counts must be generated, never remembered.

The README states how much of this repository is tests. That sentence was a
snapshot: it kept saying "9 test modules" and "1,575 of 3,635 lines" long after
the suite had grown, and nothing failed because no test recomputed it. A stale
count in a repository that publishes its own measurement surface is the same
class of defect as a stale metric in a results file.

These tests recompute the numbers from the sources on every run and compare them
with what the README claims, so the sentence is either true or red.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "README.md"

#: Build/test residue, never part of the counted surface.
EXCLUDED_PARTS = {".git", "__pycache__", ".mypy_cache", ".ruff_cache", ".pytest_cache"}

SENTENCE = re.compile(
    r"About \*\*(\d+)% of the Python here is tests\*\* — ([\d,]+) of ([\d,]+) lines "
    r"across \*\*(\d+) test modules\*\*"
)


def python_sources() -> list[Path]:
    """Every Python source file in the repository, caches excluded."""
    return sorted(
        path
        for path in ROOT.rglob("*.py")
        if not EXCLUDED_PARTS.intersection(path.relative_to(ROOT).parts)
    )


def line_count(paths: list[Path]) -> int:
    return sum(len(path.read_text(encoding="utf-8").splitlines()) for path in paths)


def measured() -> dict[str, int]:
    """The numbers a reader should be shown, computed from the tree."""
    sources = python_sources()
    tests = [path for path in sources if path.relative_to(ROOT).parts[0] == "tests"]
    total = line_count(sources)
    test_lines = line_count(tests)
    return {
        "percent": round(100 * test_lines / total),
        "test_lines": test_lines,
        "total_lines": total,
        "test_modules": len(tests),
    }


class ReadmeCountTests(unittest.TestCase):
    def setUp(self):
        self.text = README.read_text(encoding="utf-8")
        self.match = SENTENCE.search(self.text)
        self.assertIsNotNone(
            self.match,
            "README.md no longer states how much of the repository is tests; "
            "restore the sentence so the count stays checkable",
        )

    def test_the_stated_counts_match_the_sources(self):
        claimed = {
            "percent": int(self.match.group(1)),
            "test_lines": int(self.match.group(2).replace(",", "")),
            "total_lines": int(self.match.group(3).replace(",", "")),
            "test_modules": int(self.match.group(4)),
        }
        actual = measured()
        self.assertEqual(
            claimed,
            actual,
            "README.md test counts are stale: it says "
            f"{claimed['percent']}% / {claimed['test_lines']} of "
            f"{claimed['total_lines']} lines across {claimed['test_modules']} "
            f"modules, the tree measures {actual['percent']}% / "
            f"{actual['test_lines']} of {actual['total_lines']} lines across "
            f"{actual['test_modules']} modules",
        )

    def test_the_percentage_is_consistent_with_the_line_counts(self):
        test_lines, total_lines = measured()["test_lines"], measured()["total_lines"]
        self.assertEqual(
            int(self.match.group(1)),
            round(100 * test_lines / total_lines),
            "the percentage must follow from the two line counts",
        )

    def test_the_measured_surface_is_not_empty(self):
        actual = measured()
        self.assertGreater(actual["test_modules"], 0, "no test modules were found")
        self.assertLess(actual["test_lines"], actual["total_lines"])


if __name__ == "__main__":
    unittest.main()
