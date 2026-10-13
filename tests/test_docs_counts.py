"""Documentation counts must be generated, never remembered.

The README states how much of this repository is tests. That sentence was a
snapshot: it kept saying "9 test modules" and "1,575 of 3,635 lines" long after
the suite had grown, and nothing failed because no test recomputed it. A stale
count in a repository that publishes its own measurement surface is the same
class of defect as a stale metric in a results file.

These tests recompute the numbers from the sources on every run and compare them
with what the documents claim, so each sentence is either true or red:

* the README's tests-share sentence, against every Python source in the tree;
* the quickstart's version lines, against the ``VERSION`` file;
* the lock-file entry count in ``CONTRIBUTING.md``, against ``constraints.txt``;
* the latency quote in ``METHODOLOGY.md``, against the committed
  ``results.json`` it claims to quote.
"""

from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "README.md"
CONTRIBUTING = ROOT / "CONTRIBUTING.md"
QUICKSTART = ROOT / "docs" / "quickstart.md"
METHODOLOGY = ROOT / "benchmark" / "falsification" / "METHODOLOGY.md"
RESULTS_JSON = ROOT / "benchmark" / "falsification" / "results" / "results.json"
VERSION_FILE = ROOT / "VERSION"
CONSTRAINTS = ROOT / "constraints.txt"

#: Build/test residue, never part of the counted surface.
EXCLUDED_PARTS = {".git", "__pycache__", ".mypy_cache", ".ruff_cache", ".pytest_cache"}

#: A requirement line in the lock file: ``name==version``, optionally with the
#: trailing continuation backslash. Same grammar tests/test_constraints_lock.py
#: parses with, restated here so this module stays self-contained.
LOCK_PIN = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]*)==(\S+)\s*\\?$")

#: The entry-count claim in CONTRIBUTING.md ("— 52 entries, every one ...").
CONSTRAINTS_CLAIM = re.compile(r"\b(\d+) entries\b")

#: A quickstart line whose version is read from the VERSION file: the
#: provenance bullet "Skill version: `1.1.4` (from `VERSION`)", the captured
#: "VERSION     : 1.1.4" line and the "skill ver   : 1.1.4   (VERSION)" line.
QUICKSTART_VERSION_CLAIM = re.compile(
    r"(?:Skill version|VERSION|skill ver)\s*:?\s*`?(\d+\.\d+\.\d+)`?"
)

#: The latency quote in METHODOLOGY.md: "(0.013 ms and 0.052 ms per decision ...)".
METHODOLOGY_LATENCY_CLAIM = re.compile(
    r"\((\d+\.\d+) ms and (\d+\.\d+) ms per decision"
)

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


class QuickstartVersionClaimTests(unittest.TestCase):
    """Every version line in the quickstart follows the ``VERSION`` file.

    The quickstart's verified output is a captured block, but the version lines
    are not run-dependent the way ``commit`` and ``branch`` are: each one states
    that it comes from ``VERSION``. When the release moves and the captured
    block does not, the document contradicts the file it cites. That happened:
    the block said 1.1.0 while ``VERSION`` said 1.1.4.
    """

    def setUp(self):
        self.version = VERSION_FILE.read_text(encoding="utf-8").strip().lstrip("v")
        self.claims = QUICKSTART_VERSION_CLAIM.findall(
            QUICKSTART.read_text(encoding="utf-8")
        )

    def test_the_quickstart_states_the_current_version(self):
        self.assertEqual(
            self.claims,
            [self.version] * len(self.claims),
            "every quickstart version line must equal the VERSION file",
        )

    def test_the_claim_is_actually_present(self):
        """A document that stopped stating a version must not pass silently."""
        self.assertTrue(self.claims, "no quickstart version claim was found")


class ConstraintsEntryCountTests(unittest.TestCase):
    """``CONTRIBUTING.md`` counts the entries the lock file actually has.

    The lock grows with the transitive closure; the sentence did not. It said
    52 while the file pins 56, and nothing recomputed it.
    """

    def test_the_stated_entry_count_matches_the_lock(self):
        pins = [
            line
            for line in CONSTRAINTS.read_text(encoding="utf-8").splitlines()
            if LOCK_PIN.match(line.strip())
        ]
        claimed = CONSTRAINTS_CLAIM.search(CONTRIBUTING.read_text(encoding="utf-8"))
        self.assertIsNotNone(claimed, "CONTRIBUTING.md no longer states an entry count")
        self.assertEqual(
            int(claimed.group(1)),
            len(pins),
            "CONTRIBUTING.md claims "
            f"{claimed.group(1)} entries but constraints.txt pins {len(pins)}",
        )


class MethodologyLatencyClaimTests(unittest.TestCase):
    """The latency quote in METHODOLOGY.md quotes the committed run.

    The sentence says ``results.json`` records the committed run's value, so the
    check is a comparison against that artifact -- rounded the way the
    surrounding tables round (three decimals), which is how the generated
    ``RESULTS.md`` renders the same numbers.
    """

    def test_the_quoted_latency_matches_the_committed_artifact(self):
        summary = json.loads(RESULTS_JSON.read_text(encoding="utf-8"))["summary"]
        expected = tuple(
            f"{summary[policy]['mean_latency_ms_per_decision']:.3f}"
            for policy in ("single", "multi")
        )
        claimed = METHODOLOGY_LATENCY_CLAIM.search(
            METHODOLOGY.read_text(encoding="utf-8")
        )
        self.assertIsNotNone(claimed, "METHODOLOGY.md no longer quotes a latency")
        self.assertEqual(
            (claimed.group(1), claimed.group(2)),
            expected,
            "METHODOLOGY.md quotes "
            f"({claimed.group(1)} ms and {claimed.group(2)} ms) but results.json "
            f"records ({expected[0]} ms and {expected[1]} ms) for the committed run",
        )


if __name__ == "__main__":
    unittest.main()
