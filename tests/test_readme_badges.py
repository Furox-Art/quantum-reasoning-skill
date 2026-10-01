from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "README.md"

# Shields.io's PyPI Downloads endpoints proxy pypistats.org, which is
# aggressively rate limited. The badge then renders "inaccessible" or
# "rate limited by upstream service" instead of a number, so it is not a
# trustworthy signal. Point people at the PyPI stats page instead.
UNRELIABLE_BADGES = {
    "shields.io/pypi/dm": re.compile(r"shields\.io/pypi/dm", re.IGNORECASE),
    "shields.io/pypi/downloads": re.compile(r"shields\.io/pypi/downloads", re.IGNORECASE),
    "peppy.tech": re.compile(r"peppy\.tech", re.IGNORECASE),
    "degraded badge text": re.compile(r"downloads inaccessible", re.IGNORECASE),
}

PYPI_PROJECT = "https://pypi.org/project/quantum-reasoning-skill/"
PYPI_STATS = PYPI_PROJECT + "#stats"

LINKED_BADGE = re.compile(r"\[!\[[^\]]*\]\(\s*https://img\.shields\.io/[^)]*\)\]\([^)]*\)")
SHIELDS_IMAGE = re.compile(r"!\[[^\]]*\]\(\s*https://img\.shields\.io/[^)]*\)")


class ReadmeBadgeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.text = README.read_text(encoding="utf-8")

    def test_no_unreliable_dynamic_download_badges(self):
        for label, pattern in UNRELIABLE_BADGES.items():
            offending = [
                f"line {number}: {line.strip()}"
                for number, line in enumerate(self.text.splitlines(), start=1)
                if pattern.search(line)
            ]
            self.assertEqual(
                offending, [], f"README.md still uses {label}: {offending}"
            )

    def test_download_stats_link_to_pypi(self):
        self.assertIn(f"]({PYPI_STATS})", self.text)
        self.assertIn(f"]({PYPI_PROJECT})", self.text)

    def test_every_badge_has_a_link_target(self):
        residue = LINKED_BADGE.sub("", self.text)
        orphans = SHIELDS_IMAGE.findall(residue)
        self.assertEqual(orphans, [], f"README.md has unlinked badges: {orphans}")


if __name__ == "__main__":
    unittest.main()