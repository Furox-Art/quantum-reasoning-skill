"""npm may only publish the content that the version bump released.

npm 1.2.0 is the proof. The version was released and tagged on 2026-10-21, but
the first successful npm run happened on a later commit (#60 had added
unknown-flag validation to ``index.js`` in between), so the 1.2.0 tarball
carried unreleased CLI code under an already-released version number. The
README embedded in that tarball even still claimed "npm 1.2.0 was never
published". PyPI 1.2.0 was built from the tag, so the two registries served
different bytes for the same version.

npm versions are immutable, so guarding after the upload is worthless. The
publish job therefore compares every packed file against the commit that
introduced the version and refuses to continue when they differ. The tag is
deliberately not the reference: ``publish-release`` creates it only after its
own gate, so a push-triggered run would race tag creation.
"""

from __future__ import annotations

import unittest
from pathlib import Path

WORKFLOW = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "npm-publish.yml"


class NpmPublishGuardTest(unittest.TestCase):
    def setUp(self) -> None:
        self.text = WORKFLOW.read_text(encoding="utf-8")

    def test_guard_is_checked_before_packing_and_publishing(self) -> None:
        guard = self.text.index("Refuse to publish content newer than the version bump")
        self.assertLess(guard, self.text.index("Enforce the tarball content allowlist"))
        self.assertLess(guard, self.text.index('npm publish "${args[@]}"'))

    def test_guard_compares_packed_files_against_the_version_bump(self) -> None:
        self.assertIn('"rev-list", "--first-parent", "HEAD"', self.text)
        self.assertIn('"pack", "--dry-run", "--json"', self.text)
        self.assertIn("packed files differ from", self.text)
        self.assertIn("Bump the version and release the new content instead.", self.text)

    def test_publish_checkout_keeps_history_for_the_guard(self) -> None:
        checkout = self.text.index("actions/checkout@")
        guard = self.text.index("Refuse to publish content newer than the version bump")
        self.assertIn("fetch-depth: 0", self.text[checkout:guard])


if __name__ == "__main__":
    unittest.main()
