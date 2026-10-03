"""Tests that keep ``constraints.txt`` a real, fully pinned lock.

CI installs ``build`` and ``twine`` without pins, which means whatever those
distributions resolve to at release time is what builds and publishes the
package. ``constraints.txt`` closes that gap, and these tests stop it from
silently decaying back into a range list.

No network access is required: the tests only parse and check the lock file.
Advisory status is verified separately with ``pip-audit`` (OSV data).
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONSTRAINTS = ROOT / "constraints.txt"

#: A requirement line is a bare ``name==version`` optionally followed by ``\``.
PIN_RE = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]*)==([A-Za-z0-9][A-Za-z0-9.*+!-]*)\s*\\?$")
HASH_RE = re.compile(r"^--hash=sha256:([0-9a-f]{64})\s*\\?$")

#: Tools the repository pins in pyproject.toml, plus the scanner used to verify
#: this lock. A missing entry means the lock has drifted from the declared pins.
REQUIRED_TOOLS = ("build", "coverage", "mypy", "ruff", "twine", "hatchling", "pip-audit")

#: Versions pyproject.toml pins directly. These must match exactly, otherwise the
#: lock and the build configuration disagree about what CI will run.
PYPROJECT_PINS = {
    "build": "1.2.2.post1",
    "coverage": "7.6.12",
    "mypy": "1.11.2",
    "ruff": "0.7.4",
    "twine": "7.0.0",
    "hatchling": "1.32.4",
}

#: Markers that would mean the lock accepts floating versions.
FLOATING_MARKERS = (">=", "<=", "~=", "==*", " @ ", "latest")


def parse_constraints(text: str) -> dict[str, dict]:
    """Parse the lock into ``{normalised_name: {"version", "hashes"}}``."""
    entries: dict[str, dict] = {}
    for line_number, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        pin = PIN_RE.match(line)
        if pin:
            name, version = pin.group(1), pin.group(2)
            key = name.lower().replace("_", "-").replace(".", "-")
            if key in entries:
                raise AssertionError(
                    f"constraints.txt:{line_number}: {name} pinned more than once"
                )
            entries[key] = {"name": name, "version": version, "hashes": [], "line": line_number}
            continue
        digest = HASH_RE.match(line)
        if digest:
            if not entries:
                raise AssertionError(f"constraints.txt:{line_number}: hash without a pin")
            entries[key]["hashes"].append(digest.group(1))
            continue
        raise AssertionError(f"constraints.txt:{line_number}: unparseable line: {raw!r}")
    return entries


class ConstraintsLockTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not CONSTRAINTS.is_file():
            raise unittest.SkipTest("constraints.txt is not present")
        cls.text = CONSTRAINTS.read_text(encoding="utf-8")
        cls.entries = parse_constraints(cls.text)

    def test_lock_is_not_empty(self):
        self.assertGreater(len(self.entries), 0)
        self.assertGreaterEqual(len(self.entries), len(REQUIRED_TOOLS))

    def test_every_requirement_is_exactly_pinned(self):
        for key, entry in sorted(self.entries.items()):
            with self.subTest(package=key):
                self.assertIn("==", f"{entry['name']}=={entry['version']}")
                self.assertNotIn("*", entry["version"])

    def test_no_floating_specifiers_anywhere(self):
        body = "\n".join(
            line for line in self.text.splitlines() if not line.strip().startswith("#")
        )
        for marker in FLOATING_MARKERS:
            with self.subTest(marker=marker):
                self.assertNotIn(marker, body, f"lock contains floating marker {marker!r}")

    def test_every_pin_carries_at_least_one_hash(self):
        for key, entry in sorted(self.entries.items()):
            with self.subTest(package=key):
                self.assertTrue(
                    entry["hashes"],
                    f"{entry['name']} is pinned but has no sha256 hash",
                )

    def test_hashes_are_lowercase_hex_sha256(self):
        for key, entry in sorted(self.entries.items()):
            for digest in entry["hashes"]:
                with self.subTest(package=key, digest=digest[:12]):
                    self.assertRegex(digest, r"^[0-9a-f]{64}$")

    def test_no_duplicate_hashes(self):
        for key, entry in sorted(self.entries.items()):
            with self.subTest(package=key):
                self.assertEqual(
                    len(entry["hashes"]), len(set(entry["hashes"])), "duplicate hash"
                )

    def test_required_tools_are_locked(self):
        present = set(self.entries)
        for tool in REQUIRED_TOOLS:
            with self.subTest(tool=tool):
                self.assertIn(tool, present, f"{tool} is missing from the lock")

    def test_lock_agrees_with_the_pins_in_pyproject(self):
        """The lock must match the versions pyproject.toml pins directly."""
        for tool, expected in PYPROJECT_PINS.items():
            with self.subTest(tool=tool):
                entry = self.entries.get(tool)
                self.assertIsNotNone(entry, f"{tool} missing from the lock")
                self.assertEqual(
                    entry["version"],
                    expected,
                    f"constraints.txt pins {tool}=={entry['version']} but "
                    f"pyproject.toml pins {tool}=={expected}",
                )

    def test_pyproject_dev_group_is_fully_covered(self):
        """Every ``name==version`` in pyproject's dev group must appear in the lock."""
        pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        declared = set(re.findall(r'"([A-Za-z0-9][A-Za-z0-9._-]*)==([^"]+)"', pyproject))
        self.assertTrue(declared, "no pinned requirement found in pyproject.toml")
        for name, version in sorted(declared):
            key = name.lower().replace("_", "-")
            with self.subTest(requirement=name):
                entry = self.entries.get(key)
                self.assertIsNotNone(entry, f"pyproject pins {name} but the lock omits it")
                self.assertEqual(entry["version"], version)

    def test_no_top_level_install_requires_other_than_the_pin(self):
        """Nothing may smuggle in an unpinned install alongside the pins."""
        body = "\n".join(
            line for line in self.text.splitlines() if not line.strip().startswith("#")
        )
        self.assertNotIn("-r ", body)
        self.assertNotIn("--index-url", body)
        self.assertNotIn("--extra-index-url", body)

    def test_lock_documents_the_verification_command(self):
        self.assertIn("pip_audit", self.text)
        self.assertIn("OSV", self.text)


if __name__ == "__main__":
    unittest.main()
