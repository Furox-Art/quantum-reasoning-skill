"""Tests for ``bin/check_release_integrity.py``.

Background
----------
``1.1.1`` was published to npm through the ``NPM_TOKEN`` opt-in path, so it
carries no Sigstore provenance attestation; PyPI 1.1.1 carries no PEP 740
attestation either. Attestations are bound to a publish event and cannot be
backfilled, so the gap is permanent for that version.

That created a documentation risk rather than a code risk: nothing stopped a
future edit from claiming ``1.1.1`` is attested, which would be false. This
module pins the behaviour of the guard that prevents it.

Covered behaviours:

* a document asserting an attestation for an unattested release is rejected;
* a document asserting an attestation for an *attested* release is accepted;
* the disclosure cannot be deleted from the documentation;
* ``--provenance`` cannot reappear on the token publish step;
* the ``use_token_fallback`` dispatch input cannot default to ``true``;
* a registry-supplied attested set that contradicts the documentation fails,
  which is what exercises the live-data path without needing the network.

Every test injects the attested set. No test performs a registry request, so
the suite is deterministic and offline.
"""

from __future__ import annotations

import importlib.util
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GUARD = ROOT / "bin" / "check_release_integrity.py"
NPM_WORKFLOW = ROOT / ".github" / "workflows" / "npm-publish.yml"


def _load_guard():
    spec = importlib.util.spec_from_file_location("check_release_integrity", GUARD)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


guard = _load_guard()

#: What the npm attestations endpoint reports today.
REGISTRY_ATTESTED = frozenset(guard.KNOWN_ATTESTED_NPM)
#: A registry that has since attested an additional release.
REGISTRY_ATTESTED_PLUS_111 = frozenset(guard.KNOWN_ATTESTED_NPM | {"1.1.1"})


class TreeCase(unittest.TestCase):
    """Base class giving each test a disposable copy of the repository.

    The guard resolves its document and workflow paths relative to the module's
    own location, so a fixture tree has to be a full copy rather than a handful
    of stub files. Copies are small (no ``.git``) and each test gets a clean one.
    """

    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp()
        self.tree = Path(self._tmp) / "tree"
        shutil.copytree(ROOT, self.tree, ignore=shutil.ignore_patterns(".git", "__pycache__"))
        self.addCleanup(shutil.rmtree, self._tmp, ignore_errors=True)

    def patch(self, relative: str, old: str, new: str) -> None:
        """Replace ``old`` with ``new`` in a file, failing loudly if absent."""
        path = self.tree / relative
        text = path.read_text(encoding="utf-8")
        if old not in text:
            self.fail(f"fixture text not present in {relative}: {old[:80]!r}")
        path.write_text(text.replace(old, new, 1), encoding="utf-8")

    def load_guard_for(self, tree: Path):
        """Load the guard as it would be imported from inside ``tree``."""
        spec = importlib.util.spec_from_file_location(
            f"guard_{tree.name}", tree / "bin" / "check_release_integrity.py"
        )
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        return module

    def evaluate(self, tree: Path | None = None, attested: frozenset[str] = REGISTRY_ATTESTED):
        """Run every guard check against ``tree``.

        Returns the collected problems. Each load is given a unique module name so
        successive calls do not collide in ``sys.modules``.
        """
        target = tree or self.tree
        local = self.load_guard_for(target)
        problems: list[str] = []
        problems += local.check_no_unattested_version_claimed()
        problems += local.check_disclosures_match_the_registry(attested)
        problems += local.check_claims_without_registry_support(attested)
        problems += local.check_every_version_status_is_documented()
        problems += local.check_unattested_is_explicitly_disclosed()
        problems += local.check_token_path_cannot_claim_provenance()
        return problems

    # -- sentence the README uses, so fixtures can be rewritten reliably ------
    @property
    def readme_disclosure(self) -> str:
        text = (self.tree / "README.md").read_text(encoding="utf-8")
        for line in text.splitlines():
            if "was published through the long-lived-token path" in line:
                return line
        self.fail("README.md no longer contains the disclosure sentence")


class RealTreeTests(TreeCase):
    """The repository as it stands must satisfy the contract."""

    def test_real_tree_passes_with_the_registry_attested_set(self):
        self.assertEqual(self.evaluate(attested=REGISTRY_ATTESTED), [])

    def test_real_tree_passes_with_the_defaults_built_into_the_guard(self):
        local = self.load_guard_for(self.tree)
        self.assertEqual(local.check_no_unattested_version_claimed(), [])
        self.assertEqual(local.check_disclosures_match_the_registry(REGISTRY_ATTESTED), [])
        self.assertEqual(local.check_every_version_status_is_documented(), [])
        self.assertEqual(local.check_unattested_is_explicitly_disclosed(), [])
        self.assertEqual(local.check_token_path_cannot_claim_provenance(), [])


class FalseClaimTests(TreeCase):
    """A claim of an attestation that does not exist must be rejected."""

    def test_readme_claiming_1_1_1_is_attested_is_rejected(self):
        self.patch(
            "README.md",
            self.readme_disclosure,
            "Release `1.1.1` is attested. Every published release carries a Sigstore provenance\n"
            "attestation, and `1.1.1` is no exception: it carries a Sigstore provenance attestation.",
        )
        problems = self.evaluate()
        self.assertTrue(problems, "a false attestation claim must be rejected")
        self.assertTrue(
            any("README.md" in problem for problem in problems),
            f"the offending file must be named, got {problems}",
        )
        self.assertTrue(any("1.1.1" in problem for problem in problems), problems)

    def test_security_table_flipping_1_1_1_to_yes_is_rejected(self):
        self.patch(
            "SECURITY.md",
            "| `1.1.1` | npm | **no** — published via the long-lived-token path |",
            "| `1.1.1` | npm | yes — SLSA provenance attestation |",
        )
        problems = self.evaluate()
        self.assertTrue(problems, "a status table claiming an attestation must be rejected")
        self.assertTrue(any("SECURITY.md" in problem for problem in problems), problems)

    def test_changelog_claiming_1_1_1_is_attested_is_rejected(self):
        changelog = self.tree / "CHANGELOG.md"
        text = changelog.read_text(encoding="utf-8")
        anchor = "**This release was published with the token path and carries no attestation.**"
        self.assertIn(anchor, text, "CHANGELOG.md disclosure sentence moved")
        # The replacement must name the version, otherwise there is nothing for
        # the guard to attribute the claim to.
        changelog.write_text(
            text.replace(anchor, "**Release `1.1.1` is attested.**", 1), encoding="utf-8"
        )
        problems = self.evaluate()
        self.assertTrue(problems, "a CHANGELOG false claim must be rejected")
        self.assertTrue(any("CHANGELOG.md" in problem for problem in problems), problems)

    def test_claiming_1_0_0_is_attested_is_rejected(self):
        self.patch(
            "CHANGELOG.md",
            "| `1.0.0` | npm | no |",
            "| `1.0.0` | npm | yes — SLSA provenance attestation |",
        )
        problems = self.evaluate()
        self.assertTrue(problems, "1.0.0 is unattested and must not be claimed as attested")


class TrueClaimTests(TreeCase):
    """A claim about a genuinely attested release must be accepted."""

    def test_claiming_1_1_0_is_attested_is_accepted(self):
        self.patch(
            "README.md",
            "| `1.1.0` (npm) | yes — SLSA provenance and npm publish attestation, Sigstore | n/a |",
            "| `1.1.0` (npm) | yes — SLSA provenance and npm publish attestation, Sigstore | n/a |\n\n"
            "Release `1.1.0` on npm carries a Sigstore provenance attestation.",
        )
        self.assertEqual(self.evaluate(), [], "a true claim must not be rejected")


class DisclosureTests(TreeCase):
    """The disclosure cannot be quietly deleted."""

    def _delete_changelog_disclosure(self) -> None:
        changelog = self.tree / "CHANGELOG.md"
        text = changelog.read_text(encoding="utf-8")
        start = text.find("### npm attestation status")
        self.assertNotEqual(start, -1, "CHANGELOG.md disclosure section missing")
        end = text.find("### Fixed", start)
        self.assertNotEqual(end, -1, "CHANGELOG.md section after the disclosure missing")
        changelog.write_text(text[:start] + text[end:], encoding="utf-8")

    def test_deleting_the_changelog_disclosure_is_rejected(self):
        self._delete_changelog_disclosure()
        problems = self.evaluate()
        self.assertTrue(
            problems,
            "removing the attestation disclosure must be rejected",
        )

    def test_deleting_every_mention_of_1_1_1_is_rejected(self):
        """Silently omitting the unattested release is also a failure."""
        for relative in ("README.md", "SECURITY.md", "CHANGELOG.md"):
            path = self.tree / relative
            text = path.read_text(encoding="utf-8")
            path.write_text(text.replace("1.1.1", "1.1.2"), encoding="utf-8")
        problems = self.evaluate()
        self.assertTrue(
            problems,
            "an unattested release must be stated, not merely omitted",
        )

    def test_removing_every_disclosure_is_rejected(self):
        """Deleting the disclosure from one file is survivable; from all is not.

        The guard only requires that a disclosure exists *somewhere*, so removing
        the README section alone must stay green while `SECURITY.md` still
        discloses. Removing all of them must fail.
        """
        readme = self.tree / "README.md"
        text = readme.read_text(encoding="utf-8")
        start = text.find("### Supply-chain attestations")
        self.assertNotEqual(start, -1, "README.md disclosure section missing")
        end = text.find("\n## ", start)
        self.assertNotEqual(end, -1, "README.md section after the disclosure missing")
        readme.write_text(text[:start] + text[end:], encoding="utf-8")

        security = self.tree / "SECURITY.md"
        sec = security.read_text(encoding="utf-8")
        sec_start = sec.find("## Supply-chain attestations")
        self.assertNotEqual(sec_start, -1, "SECURITY.md disclosure section missing")
        security.write_text(sec[:sec_start], encoding="utf-8")

        self._delete_changelog_disclosure()

        self.assertTrue(
            self.evaluate(),
            "removing every attestation disclosure must be rejected",
        )

    def test_removing_the_readme_section_alone_is_tolerated(self):
        """One surviving disclosure is enough; this is a deliberate non-regression."""
        readme = self.tree / "README.md"
        text = readme.read_text(encoding="utf-8")
        start = text.find("### Supply-chain attestations")
        self.assertNotEqual(start, -1, "README.md disclosure section missing")
        end = text.find("\n## ", start)
        readme.write_text(text[:start] + text[end:], encoding="utf-8")
        self.assertEqual(
            self.evaluate(),
            [],
            "SECURITY.md still discloses, so removing only the README section is fine",
        )


class TokenPublishPathTests(TreeCase):
    """The token path must never claim provenance or activate after OIDC failure."""

    def test_provenance_on_the_token_step_is_rejected(self):
        self.patch(
            ".github/workflows/npm-publish.yml",
            "        run: npm publish --access public\n",
            "        run: npm publish --access public --provenance\n",
        )
        problems = self.evaluate()
        self.assertTrue(problems, "a token publish claiming provenance must be rejected")
        self.assertTrue(
            any("cannot mint a Sigstore attestation" in problem for problem in problems),
            f"the reason must be reported, got {problems}",
        )

    def test_dispatch_input_defaulting_to_true_is_rejected(self):
        self.patch(
            ".github/workflows/npm-publish.yml",
            "        default: false",
            "        default: true",
        )
        problems = self.evaluate()
        self.assertTrue(problems, "defaulting use_token_fallback to true must be rejected")
        self.assertTrue(any("default to false" in problem for problem in problems), problems)

    def test_removing_id_token_permission_is_rejected(self):
        self.patch(
            ".github/workflows/npm-publish.yml",
            "      id-token: write",
            "      contents: read",
        )
        problems = self.evaluate()
        self.assertTrue(problems, "dropping id-token: write must be rejected")

    def test_post_failure_token_fallback_is_rejected(self):
        """Credential choice must happen before upload, never after OIDC fails."""
        self.patch(
            ".github/workflows/npm-publish.yml",
            "        if: steps.gate.outputs.skip != 'true' && steps.mode.outputs.requested == 'token'",
            "        if: steps.trusted.outcome != 'success'",
        )
        local = self.load_guard_for(self.tree)
        problems = local.check_token_path_cannot_claim_provenance()
        self.assertTrue(
            problems,
            "a token retry keyed on OIDC failure must be rejected",
        )
        self.assertTrue(any("post-failure fallback" in problem for problem in problems), problems)

    def test_oidc_step_remaining_the_default_is_enforced(self):
        local = self.load_guard_for(self.tree)
        text = (self.tree / ".github" / "workflows" / "npm-publish.yml").read_text(encoding="utf-8")
        self.assertIn(
            "steps.mode.outputs.requested == 'trusted'",
            text,
            local and "OIDC must stay the default",
        )


class RegistryDisagreementTests(TreeCase):
    """The live-data path: a registry set that contradicts the docs must fail.

    The set is injected rather than fetched, so the contract is exercised without
    network access. In CI the same check receives the set from the live npm
    attestations endpoint.
    """

    def test_registry_reporting_1_1_1_attested_contradicts_the_documentation(self):
        problems = self.evaluate(attested=REGISTRY_ATTESTED_PLUS_111)
        self.assertTrue(
            problems,
            "a registry reporting 1.1.1 as attested must contradict the disclosure",
        )
        self.assertTrue(any("1.1.1" in problem for problem in problems), problems)

    def test_registry_reporting_nothing_attested_contradicts_the_documentation(self):
        problems = self.evaluate(attested=frozenset())
        self.assertTrue(
            problems,
            "a registry reporting no attestations must contradict the 1.1.0 claim",
        )
        self.assertTrue(any("1.1.0" in problem for problem in problems), problems)

    def test_registry_reporting_a_version_not_documented_is_flagged(self):
        problems = self.evaluate(attested=frozenset({"1.0.0", "9.9.9"}))
        self.assertTrue(
            problems,
            "a registry reporting an undocumented version must be surfaced",
        )

    def test_exact_registry_match_passes(self):
        self.assertEqual(self.evaluate(attested=REGISTRY_ATTESTED), [])


class WorkflowWiringTests(unittest.TestCase):
    """The guard and this test must both be wired into CI."""

    def setUp(self) -> None:
        self.workflow = (ROOT / ".github" / "workflows" / "validate-skill.yml").read_text(
            encoding="utf-8"
        )

    def test_guard_is_required_by_the_repository_contract(self):
        self.assertIn("bin/check_release_integrity.py", self.workflow)

    def test_attested_set_is_queried_from_the_registry(self):
        # The URL is split across lines in the workflow, so match the two halves.
        self.assertIn("registry.npmjs.org/-/npm/v1/attestations/", self.workflow)
        self.assertIn("quantum-reasoning-skill", self.workflow)
        self.assertIn("--attested-npm", self.workflow)
        self.assertIn("urllib.request", self.workflow)

    def test_npm_workflow_verifies_its_own_attestation(self):
        publish = (ROOT / ".github" / "workflows" / "npm-publish.yml").read_text(encoding="utf-8")
        self.assertIn(
            "Verify the default publish is attested",
            publish,
            "the publish path must confirm the registry stored an attestation",
        )

    def test_guard_script_exists_and_is_non_empty(self):
        self.assertTrue(GUARD.is_file(), "bin/check_release_integrity.py is missing")
        self.assertGreater(GUARD.stat().st_size, 0)

    def test_publish_workflow_binds_the_expected_environment(self):
        publish = (ROOT / ".github" / "workflows" / "npm-publish.yml").read_text(encoding="utf-8")
        self.assertIn("environment: npm", publish)
        self.assertIn("id-token: write", publish)


class GuardUnitTests(unittest.TestCase):
    """Direct checks on the guard's decision logic, independent of any file."""

    def test_known_sets_are_disjoint(self):
        self.assertEqual(
            guard.KNOWN_ATTESTED_NPM & guard.KNOWN_UNATTESTED_NPM,
            frozenset(),
            "a version cannot be both attested and unattested",
        )

    def test_1_1_1_is_knowingly_unattested(self):
        """The reason this module exists: 1.1.1 has no attestation."""
        self.assertIn("1.1.1", guard.KNOWN_UNATTESTED_NPM)
        self.assertNotIn("1.1.1", guard.KNOWN_ATTESTED_NPM)

    def test_sentence_splitter_keeps_release_claims_separate(self):
        # A claim about one release must not be read as a claim about another.
        text = (
            "Use `1.1.0`, which carries an attestation. "
            "Do not treat the absence of an attestation on `1.1.1` as evidence of tampering."
        )
        chunks = guard.sentences(text)
        self.assertEqual(len(chunks), 2, chunks)
        self.assertNotIn("1.1.1", chunks[0])
        self.assertIn("1.1.1", chunks[1])

    def test_tight_claim_matches_a_bare_adjectival_claim(self):
        self.assertTrue(guard.TIGHT_CLAIM.search("`1.1.1` is attested"))
        self.assertTrue(
            guard.TIGHT_CLAIM.search("`1.1.1` carries a Sigstore provenance attestation")
        )

    def test_tight_denial_matches_disclosures(self):
        self.assertTrue(guard.TIGHT_DENIAL.search("carries no attestation"))
        self.assertTrue(guard.TIGHT_DENIAL.search("unattested"))
        self.assertFalse(
            guard.TIGHT_DENIAL.search("`1.1.1` is attested"), "a claim is not a denial"
        )

    def test_attestation_mention_covers_inflections(self):
        for word in ("attestation", "attestations", "attested", "attesting"):
            self.assertTrue(guard.ATTESTATION_MENTION.search(word), word)

    def test_registry_probe_uses_the_documented_endpoint(self):
        """The guard's constants must stay aligned with what CI queries."""
        self.assertIn(
            "https://registry.npmjs.org/-/npm/v1/attestations/",
            (ROOT / ".github" / "workflows" / "validate-skill.yml").read_text(encoding="utf-8"),
        )

    def test_version_token_recognises_three_component_versions(self):
        self.assertEqual(guard.version_mentions("shipped in 1.1.1 and 1.0.0"), {"1.1.1", "1.0.0"})

    def test_no_document_names_an_unattested_version_as_attested(self):
        """A belt-and-braces read of the real corpus."""
        for path in guard.doc_files():
            text = path.read_text(encoding="utf-8")
            relative = path.relative_to(ROOT).as_posix()
            for chunk in guard.sentences(text):
                if not guard.ATTESTATION_MENTION.search(chunk):
                    continue
                if not guard.version_mentions(chunk) & guard.KNOWN_UNATTESTED_NPM:
                    continue
                self.assertFalse(
                    guard.TIGHT_CLAIM.search(chunk) and not guard.TIGHT_DENIAL.search(chunk),
                    f"{relative} appears to claim an attestation: {chunk.strip()[:120]!r}",
                )


if __name__ == "__main__":
    unittest.main()
