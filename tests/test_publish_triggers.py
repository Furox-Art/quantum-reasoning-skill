"""The publishing triggers must cover every file that can change a release.

A GitHub Actions ``paths`` filter is an allowlist: a commit that only touches
files outside it never runs the publish job. When the version is new and
unpublished, the effect is a release that silently never happens -- the next
change inside the filter publishes it, carrying whatever had drifted in the
meantime. That is how a benchmark-harness or citation-file edit reaches the
registry attached to the wrong build.

The two publishing workflows are therefore checked against the packaging
configuration itself rather than against a hand-maintained copy of it:

* ``pypi-release.yml`` must cover every input hatchling reads to build the wheel
  and the sdist -- the ``only-include`` and ``include`` lists, the
  ``force-include`` sources, the project readme, and the files the job's own
  release gates read;
* ``npm-publish.yml`` must cover every input ``npm pack`` reads -- the ``files``
  allowlist, ``package.json`` itself and ``.npmignore``.

On top of the artifact inputs, both filters must list the version-bearing
citation surfaces (``CITATION.cff`` and ``codemeta.json``). Neither ships in
the npm tarball and only ``CITATION.cff`` ships in the sdist, but both carry
the release version, so an edit to one is a release-affecting change that has
to re-run the release gates. This is not hypothetical: ``codemeta.json`` said
``1.1.0`` while 1.1.2 shipped (recorded in CHANGELOG.md under 1.1.3), and
nothing at the time re-ran the gates on a metadata-only edit. The publish jobs
are idempotent -- they no-op when the version is already published -- so
listing metadata cannot cause an accidental republish.

``codemeta.json`` remains absent from the packaging configuration, and that is
asserted from the packaging configuration rather than assumed: adding it to a
wheel or sdist has to move it into the filter too. Asserting the derived sets,
rather than a snapshot, is what keeps the filter honest when packaging changes.
"""

from __future__ import annotations

import importlib.util
import json
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import conftest  # noqa: E402  (repository root is on sys.path only after the insert)

WORKFLOW_DIR = ROOT / ".github" / "workflows"
PYPROJECT = ROOT / "pyproject.toml"
PACKAGE_JSON = ROOT / "package.json"


def _load_checker():
    spec = importlib.util.spec_from_file_location(
        "check_workflows", ROOT / "bin" / "check_workflows.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


checker = _load_checker()


def load_document(name: str):
    """Parse a workflow with the repository's duplicate-rejecting loader."""
    return checker.strict_load((WORKFLOW_DIR / name).read_text(encoding="utf-8"), source=name)


def triggers(document) -> dict:
    # PyYAML resolves the bare `on:` key to the boolean True.
    return document[True] if True in document else document["on"]


def push_paths(name: str) -> list[str]:
    return list(triggers(load_document(name))["push"]["paths"])


def glob_to_regex(pattern: str) -> re.Pattern[str]:
    """Translate a GitHub path-filter glob into a regex.

    ``*`` does not cross a directory separator and ``**`` does, which is what
    makes ``docs/**`` cover the tree while ``docs`` covers nothing.
    """
    out: list[str] = []
    index = 0
    while index < len(pattern):
        if pattern.startswith("**/", index):
            out.append("(?:.*/)?")
            index += 3
        elif pattern.startswith("**", index):
            out.append(".*")
            index += 2
        elif pattern[index] == "*":
            out.append("[^/]*")
            index += 1
        elif pattern[index] == "?":
            out.append("[^/]")
            index += 1
        else:
            out.append(re.escape(pattern[index]))
            index += 1
    return re.compile("".join(out) + r"\Z")


def covered(path: str, patterns: list[str]) -> bool:
    """True when some filter entry matches ``path`` (or its directory contents)."""
    for pattern in patterns:
        regex = glob_to_regex(pattern)
        if regex.fullmatch(path) or regex.fullmatch(f"{path}/**"):
            return True
    return False


def _readme_of(text: str) -> str:
    match = re.search(r'^readme\s*=\s*"([^"]+)"', text, re.MULTILINE)
    if match is None:
        raise AssertionError("pyproject.toml does not declare project.readme")
    return match.group(1)


def _hatch_string_list(text: str, key: str) -> list[str]:
    """Values of a hatch ``key = [ ... ]`` array.

    Parsed as text rather than with tomllib: the supported interpreter floor
    is 3.10, which has no stdlib TOML parser, and a packaging-gap guard that
    cannot import is the very class of silent gap this test exists to catch.
    """
    match = re.search(rf"^{re.escape(key)}\s*=\s*\[(.*?)\]", text, re.DOTALL | re.MULTILINE)
    if match is None:
        return []
    return re.findall(r'"([^"]*)"', match.group(1))


def _hatch_force_include_keys(text: str) -> list[str]:
    """Keys of a hatch ``[tool.hatch.build.targets.<t>.force-include]`` table."""
    keys: list[str] = []
    in_table = False
    for line in text.splitlines():
        if line.strip().startswith("["):
            in_table = line.strip().endswith("force-include]")
            continue
        if in_table:
            match = re.match(r'^"([^"]+)"\s*=', line.strip())
            if match:
                keys.append(match.group(1))
    return keys


def pypi_artifact_inputs() -> set[str]:
    """Every repository path hatchling reads to build the distributions."""
    text = PYPROJECT.read_text(encoding="utf-8")
    paths = {_readme_of(text)}
    # The build definition itself, and the version file the job cross-checks.
    paths.update({"pyproject.toml", "VERSION"})
    paths.update(_hatch_string_list(text, "only-include"))
    paths.update(_hatch_string_list(text, "include"))
    paths.update(_hatch_force_include_keys(text))
    # A leading slash is a "repo-root relative" marker in hatchling, not a path.
    return {path.lstrip("/") for path in paths}


def npm_artifact_inputs() -> set[str]:
    """Every repository path ``npm pack`` reads."""
    document = json.loads(PACKAGE_JSON.read_text(encoding="utf-8"))
    paths = set(document.get("files", []))
    paths.update({"package.json", ".npmignore"})
    return paths


#: The version-bearing citation surfaces. They are part of a release even where
#: they ship in no artifact, so both publishing filters must list them.
RELEASE_METADATA_SURFACES = ("CITATION.cff", "codemeta.json")

#: The filters as they stood when the audit ran: the PyPI list already carried
#: ``CITATION.cff`` (added with the sdist inputs) but not ``codemeta.json``; the
#: npm list carried neither.
AUDITED_PYPI_PATHS = [
    ".github/pypi-release-trigger",
    ".github/**",
    "pyproject.toml",
    "VERSION",
    "README.md",
    "LICENSE",
    "SKILL.md",
    "CHANGELOG.md",
    "CONTRIBUTING.md",
    "SECURITY.md",
    "CITATION.cff",
    "index.js",
    "package.json",
    "quantum_reasoning_skill/**",
    "reference/**",
    "benchmark/**",
    "docs/**",
    "examples/**",
    "bin/**",
    "tests/**",
]
AUDITED_NPM_PATHS = [
    "package.json",
    "index.js",
    "VERSION",
    "SKILL.md",
    "LICENSE",
    "README.md",
    ".npmignore",
]


class PathFilterMatcherTests(unittest.TestCase):
    """The matcher must not over- or under-report coverage."""

    def test_double_star_covers_a_whole_tree(self):
        self.assertTrue(covered("reference/branch_controller.py", ["reference/**"]))
        self.assertTrue(covered("reference/a/b/c.py", ["reference/**"]))

    def test_a_sibling_with_a_shared_prefix_is_not_covered(self):
        self.assertFalse(covered("reference-notes/x.py", ["reference/**"]))
        self.assertFalse(covered("docsx/index.html", ["docs/**"]))

    def test_a_bare_name_does_not_cover_a_directory(self):
        """This is the trap: ``- reference`` matches no file at all."""
        self.assertFalse(covered("reference/branch_controller.py", ["reference"]))

    def test_a_star_does_not_cross_a_separator(self):
        self.assertTrue(covered("index.js", ["*.js"]))
        self.assertFalse(covered("sub/index.js", ["*.js"]))
        self.assertTrue(covered("sub/index.js", ["**/*.js"]))

    def test_an_exact_file_is_covered(self):
        self.assertTrue(covered("pyproject.toml", ["pyproject.toml"]))
        self.assertFalse(covered("pyproject.toml", ["pyproject.toml.bak"]))


class PypiPublishTriggerTests(unittest.TestCase):
    def setUp(self):
        self.paths = push_paths("pypi-release.yml")

    def test_every_artifact_input_is_covered(self):
        missing = sorted(path for path in pypi_artifact_inputs() if not covered(path, self.paths))
        self.assertEqual(missing, [], f"pypi-release.yml paths miss {missing}")

    def test_the_trigger_event_and_branch_are_unchanged(self):
        document = load_document("pypi-release.yml")
        push = triggers(document)["push"]
        self.assertEqual(push["branches"], ["main"])
        self.assertEqual(sorted(triggers(document)), ["push", "workflow_dispatch"])

    def test_the_manual_trigger_file_is_still_listed(self):
        self.assertIn(".github/pypi-release-trigger", self.paths)

    def test_no_duplicate_or_overbroad_entries(self):
        duplicates = {path for path in self.paths if self.paths.count(path) > 1}
        self.assertEqual(duplicates, set(), f"duplicate path filters: {duplicates}")
        self.assertNotIn("**", self.paths, "a bare ** triggers on every push")

    def test_codemeta_json_ships_in_no_artifact(self):
        """Documented, verified packaging fact rather than an accidental omission.

        ``codemeta.json`` is in neither the wheel's ``only-include`` nor the
        sdist's ``include``, so it cannot change what either registry serves.
        It is asserted absent from the artifact inputs so that adding it to
        packaging has to move it into the filter too. Being outside the
        artifact does not put it outside the *release*: it carries the release
        version, so it belongs in the trigger anyway -- pinned by
        :class:`ReleaseMetadataTriggerTests`.
        """
        self.assertNotIn("codemeta.json", pypi_artifact_inputs())
        self.assertNotIn("codemeta.json", npm_artifact_inputs())


class ReleaseMetadataTriggerTests(unittest.TestCase):
    """The version-bearing citation surfaces belong in both publishing filters.

    Read back from the parsed workflow YAML rather than grepped from the file,
    so the pin cannot be satisfied by a comment or a stray string.
    """

    def test_the_metadata_surfaces_are_in_both_triggers(self):
        for workflow in ("pypi-release.yml", "npm-publish.yml"):
            paths = push_paths(workflow)
            for surface in RELEASE_METADATA_SURFACES:
                self.assertIn(
                    surface,
                    paths,
                    f"{workflow} paths miss {surface}; a release-metadata edit "
                    "would never re-run the release gates",
                )

    def test_the_pins_survive_a_real_yaml_parse(self):
        """The paths are read through the duplicate-rejecting loader."""
        for workflow in ("pypi-release.yml", "npm-publish.yml"):
            document = load_document(workflow)
            push = triggers(document)["push"]
            self.assertEqual(push["branches"], ["main"])
            for surface in RELEASE_METADATA_SURFACES:
                self.assertIn(surface, list(push["paths"]), workflow)

    def test_the_audited_filters_missed_them(self):
        """Negative control: the exclusion the audit flagged really was a gap.

        Before the widening, the PyPI filter had ``CITATION.cff`` but no
        ``codemeta.json``, and the npm filter had neither. Replaying those
        audited lists through the same matcher shows the failure mode.
        """
        pypi_missing = [
            surface
            for surface in RELEASE_METADATA_SURFACES
            if not covered(surface, AUDITED_PYPI_PATHS)
        ]
        self.assertEqual(pypi_missing, ["codemeta.json"])
        npm_missing = [
            surface
            for surface in RELEASE_METADATA_SURFACES
            if not covered(surface, AUDITED_NPM_PATHS)
        ]
        self.assertEqual(npm_missing, list(RELEASE_METADATA_SURFACES))


class NpmPublishTriggerTests(unittest.TestCase):
    def setUp(self):
        self.paths = push_paths("npm-publish.yml")

    def test_every_artifact_input_is_covered(self):
        missing = sorted(path for path in npm_artifact_inputs() if not covered(path, self.paths))
        self.assertEqual(missing, [], f"npm-publish.yml paths miss {missing}")

    def test_the_trigger_event_and_branch_are_unchanged(self):
        document = load_document("npm-publish.yml")
        push = triggers(document)["push"]
        self.assertEqual(push["branches"], ["main"])
        self.assertEqual(sorted(triggers(document)), ["push", "workflow_dispatch"])

    def test_the_tarball_allowlist_is_not_triggering_only_on_the_launcher(self):
        """README.md and LICENSE are packed, so they must trigger as well."""
        self.assertIn("README.md", self.paths)
        self.assertIn("LICENSE", self.paths)

    def test_the_fixture_that_used_to_fail_now_fails(self):
        """Negative control: the pre-widening filter must not cover the tarball."""
        stale = ["package.json", "index.js", "VERSION", "SKILL.md"]
        self.assertEqual(
            sorted(p for p in npm_artifact_inputs() if not covered(p, stale)),
            [".npmignore", "LICENSE", "README.md"],
        )


class VersionSurfaceTests(unittest.TestCase):
    """Every version-bearing surface must agree before a release."""

    def test_the_real_tree_is_in_lockstep_everywhere(self):
        self.assertEqual(conftest.release_version_failures(), [])

    def test_codemeta_and_skill_versions_are_read(self):
        self.assertEqual(conftest.codemeta_version(), conftest.repo_version())
        self.assertEqual(conftest.skill_front_matter_version(), conftest.repo_version())

    def test_prereleases_are_recognised_but_build_metadata_is_not(self):
        self.assertTrue(conftest.is_prerelease("1.3.0-rc.1"))
        self.assertTrue(conftest.is_prerelease("1.3.0-beta.2+build.5"))
        self.assertFalse(conftest.is_prerelease("1.3.0"))
        self.assertFalse(conftest.is_prerelease("1.3.0+build.5"))


class PrereleasePolicyTests(unittest.TestCase):
    """The release path either handles or blocks prereleases, never half-way."""

    def test_both_release_workflows_use_the_shared_detector(self):
        for workflow in ("publish-release.yml", "npm-publish.yml"):
            text = (WORKFLOW_DIR / workflow).read_text(encoding="utf-8")
            self.assertIn("conftest.is_prerelease", text, workflow)

    def test_npm_prereleases_do_not_move_latest(self):
        text = (WORKFLOW_DIR / "npm-publish.yml").read_text(encoding="utf-8")
        self.assertIn("args+=(--tag next)", text)
        self.assertIn('PRERELEASE: ${{ steps.meta.outputs.prerelease }}', text)


if __name__ == "__main__":
    unittest.main()
