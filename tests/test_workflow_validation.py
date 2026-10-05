"""Tests for ``bin/check_workflows.py``.

``npm-publish.yml`` reached ``main`` with ``shell``, ``env`` and ``run`` each
defined twice in a single step. GitHub rejects the whole workflow at parse time,
so ``gh workflow run npm-publish.yml`` returned HTTP 422 and no publish could
start.

It shipped because every "does the YAML parse?" check in this repository used
``yaml.safe_load``, which resolves duplicate keys silently by keeping the last
value. The broken file parsed fine under that loader.

These tests pin the replacement behaviour:

* the loader used here **raises** on a duplicate key, where ``safe_load`` does not;
* every workflow in the repository validates;
* each step declares its singleton keys once;
* steps carry exactly one of ``run`` or ``uses``;
* step shell bodies are syntactically valid bash.

The negative controls reintroduce the exact defect from ``main`` and assert it is
caught, so the check cannot silently regress to a permissive parse.
"""

from __future__ import annotations

import contextlib
import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "bin" / "check_workflows.py"


def _load():
    spec = importlib.util.spec_from_file_location("check_workflows", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


checker = _load()

#: A minimal valid workflow, used as the base for fixtures.
VALID_WORKFLOW = """\
name: ci

on:
  push:
    branches: [main]

permissions:
  contents: read

jobs:
  build:
    name: build
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@abc
      - name: Say hello
        shell: bash
        run: |
          set -euo pipefail
          echo hello
"""

#: The defect that reached main: a step whose `shell`, `env` and `run` keys are
#: each defined twice. The second block is a copy of an earlier step's body.
DUPLICATE_KEYS_WORKFLOW = """\
name: ci

on:
  push:
    branches: [main]

permissions:
  contents: read

jobs:
  build:
    name: build
    runs-on: ubuntu-latest
    steps:
      - name: Verify something
        shell: bash
        env:
          NAME: thing
        run: |
          set -euo pipefail
          echo first
        shell: bash
        env:
          NAME: thing
        run: |
          set -euo pipefail
          echo second
"""


class LoaderTests(unittest.TestCase):
    """The loader must reject what ``yaml.safe_load`` accepts."""

    def test_strict_loader_raises_on_a_duplicate_key(self):
        with self.assertRaises(checker.DuplicateKeyError):
            checker.strict_load(DUPLICATE_KEYS_WORKFLOW, source="fixture")

    def test_safe_load_accepts_the_same_document(self):
        """This is the hole: the default loader passes the broken file."""
        import yaml

        parsed = yaml.safe_load(DUPLICATE_KEYS_WORKFLOW)
        self.assertIn("jobs", parsed, "safe_load parses the broken document")
        # It silently keeps the last value, discarding the first body.
        body = parsed["jobs"]["build"]["steps"][0]["run"]
        self.assertIn("echo second", body)
        self.assertNotIn("echo first", body)

    def test_strict_loader_accepts_a_valid_document(self):
        parsed = checker.strict_load(VALID_WORKFLOW, source="fixture")
        self.assertEqual(parsed["name"], "ci")

    def test_valid_workflow_has_no_duplicate_reports(self):
        self.assertEqual(checker._raw_key_counts(VALID_WORKFLOW), [])

    def test_duplicate_reports_name_the_key_and_both_lines(self):
        findings = checker._raw_key_counts(DUPLICATE_KEYS_WORKFLOW)
        keys = {key for key, _, _ in findings}
        self.assertEqual(keys, {"shell", "env", "run"}, findings)
        for key, second, first in findings:
            self.assertGreater(second, first, f"{key}: second line must follow the first")


class StructureTests(unittest.TestCase):
    """Structural rules, checked without needing a file on disk."""

    def _validate(self, text: str) -> list[str]:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "workflow.yml"
            path.write_text(text, encoding="utf-8")
            original_root = checker.ROOT
            checker.ROOT = Path(tmp)
            try:
                return checker.check_workflow_structure(path)
            finally:
                checker.ROOT = original_root

    def test_valid_workflow_produces_no_problems(self):
        self.assertEqual(self._validate(VALID_WORKFLOW), [])

    def test_duplicate_keys_are_reported(self):
        problems = self._validate(DUPLICATE_KEYS_WORKFLOW)
        self.assertTrue(problems, "the shipped defect must be reported")
        self.assertTrue(
            any("duplicate mapping key" in problem for problem in problems), problems
        )

    def test_step_with_both_run_and_uses_is_rejected(self):
        """A step doing both is invalid; keep the keys in a distinct block so the
        fixture does not also trip the duplicate-key rule."""
        text = VALID_WORKFLOW.replace(
            "      - name: Say hello\n        shell: bash\n        run: |\n"
            "          set -euo pipefail\n          echo hello\n",
            "      - name: Say hello\n"
            "        uses: actions/checkout@abc\n"
            "        shell: bash\n"
            "        run: |\n"
            "          set -euo pipefail\n"
            "          echo hello\n",
        )
        problems = self._validate(text)
        self.assertTrue(
            any("both 'run' and 'uses'" in problem for problem in problems),
            problems,
        )

    def test_step_with_neither_run_nor_uses_is_rejected(self):
        text = VALID_WORKFLOW.replace(
            "      - name: Say hello\n        shell: bash\n        run: |\n"
            "          set -euo pipefail\n          echo hello\n",
            "      - name: Say hello\n        shell: bash\n",
        )
        problems = self._validate(text)
        self.assertTrue(
            any("neither 'run' nor 'uses'" in problem for problem in problems), problems
        )

    @unittest.skipIf(checker.usable_bash() is None, "no working bash on this platform")
    def test_invalid_bash_in_a_step_is_rejected(self):
        text = VALID_WORKFLOW.replace("          echo hello\n", "          if [ ; then\n")
        problems = self._validate(text)
        self.assertTrue(any("not valid bash" in problem for problem in problems), problems)

    def test_the_wsl_launcher_stub_is_rejected(self):
        """Regression: `bash` on a Windows runner is the WSL launcher stub.

        It exits non-zero for any input, including valid script, so treating its
        exit status as a syntax verdict reported all 50 step bodies across all
        four workflows as invalid bash on windows-latest. Requiring
        ``$BASH_VERSION`` is what distinguishes it from a real bash.
        """
        with self._probe_returning(1):
            self.assertFalse(checker._is_usable_bash("bash"))

    def test_a_working_bash_is_accepted(self):
        """The other half: a real bash must not be skipped."""
        with self._probe_returning(0):
            self.assertTrue(checker._is_usable_bash("bash"))

    def test_an_os_error_while_probing_is_rejected(self):
        def explode(*_args, **_kwargs):
            raise OSError("no such file")

        with self._patched_run(explode):
            self.assertFalse(checker._is_usable_bash("bash"))

    def test_a_hanging_bash_is_rejected(self):
        def timeout(*_args, **_kwargs):
            raise subprocess.TimeoutExpired(cmd="bash", timeout=60)

        with self._patched_run(timeout):
            self.assertFalse(checker._is_usable_bash("bash"))

    def test_a_non_file_candidate_is_never_selected(self):
        """A path that does not exist must be discarded before probing."""
        with tempfile.TemporaryDirectory() as tmp:
            absent = str(Path(tmp) / "sub" / "bash.exe")
            original_which = checker.shutil.which
            original_candidates = checker.WINDOWS_BASH_CANDIDATES
            try:
                checker.shutil.which = lambda _n: absent  # type: ignore[assignment]
                checker.WINDOWS_BASH_CANDIDATES = (absent,)
                checker._BASH = checker._UNPROBED
                self.assertIsNone(checker.usable_bash())
            finally:
                checker.shutil.which = original_which  # type: ignore[assignment]
                checker.WINDOWS_BASH_CANDIDATES = original_candidates
                checker._BASH = checker._UNPROBED

    @contextlib.contextmanager
    def _patched_run(self, fake):
        original = checker.subprocess.run
        checker.subprocess.run = fake  # type: ignore[assignment]
        try:
            yield
        finally:
            checker.subprocess.run = original  # type: ignore[assignment]

    @contextlib.contextmanager
    def _probe_returning(self, returncode: int):
        class Result:
            pass

        result = Result()
        result.returncode = returncode

        def fake(_args, **_kwargs):
            return result

        with self._patched_run(fake):
            yield

    def test_no_usable_bash_skips_the_syntax_check_entirely(self):
        """With no bash at all, steps are not reported as invalid."""
        original_which = checker.shutil.which
        original_candidates = checker.WINDOWS_BASH_CANDIDATES
        try:
            checker.shutil.which = lambda _n: None  # type: ignore[assignment]
            checker.WINDOWS_BASH_CANDIDATES = ()
            checker._BASH = checker._UNPROBED
            self.assertIsNone(checker.usable_bash())
            checker._BASH = checker._UNPROBED
            problems = self._validate(VALID_WORKFLOW)
        finally:
            checker.shutil.which = original_which  # type: ignore[assignment]
            checker.WINDOWS_BASH_CANDIDATES = original_candidates
            checker._BASH = checker._UNPROBED
        self.assertEqual(
            problems,
            [],
            "an unusable bash must be skipped, not reported as invalid syntax",
        )

    def test_duplicate_name_at_workflow_level_is_rejected(self):
        text = VALID_WORKFLOW.replace("name: ci\n", "name: ci\nname: ci-again\n", 1)
        problems = self._validate(text)
        # The strict loader catches this first, which is the intended order.
        self.assertTrue(
            any("duplicate mapping key" in problem for problem in problems), problems
        )


class RepositoryWorkflowTests(unittest.TestCase):
    """Every workflow actually in the repository must validate."""

    def test_all_repository_workflows_validate(self):
        files = checker.workflow_files()
        self.assertGreater(len(files), 0, "no workflow files found")
        problems: list[str] = []
        for path in files:
            problems.extend(checker.check_workflow_structure(path))
        self.assertEqual(problems, [], problems)

    def test_npm_publish_workflow_has_no_duplicate_step_keys(self):
        path = ROOT / ".github" / "workflows" / "npm-publish.yml"
        self.assertTrue(path.is_file(), "npm-publish.yml is missing")
        self.assertEqual(checker._raw_key_counts(path.read_text(encoding="utf-8")), [])

    def test_npm_publish_parses_with_the_strict_loader(self):
        path = ROOT / ".github" / "workflows" / "npm-publish.yml"
        parsed = checker.strict_load(path.read_text(encoding="utf-8"), source="npm-publish")
        self.assertIn("publish", parsed["jobs"], "the publish job must survive parsing")


class PublishBehaviourTests(unittest.TestCase):
    """The repaired workflow must keep every behaviour it had before.

    Traces the parsed job so a future edit cannot quietly drop a step, and pins
    what happens on a push versus a dispatch with the token opt-in set.
    """

    def setUp(self) -> None:
        self.path = ROOT / ".github" / "workflows" / "npm-publish.yml"
        self.text = self.path.read_text(encoding="utf-8")
        self.document = checker.strict_load(self.text, source="npm-publish")
        self.job = self.document["jobs"]["publish"]
        self.steps = self.job["steps"]

    def _step(self, name: str) -> dict:
        for step in self.steps:
            if step.get("name") == name:
                return step
        self.fail(f"step {name!r} is missing from npm-publish.yml")

    # -- structure -----------------------------------------------------------
    def test_credential_mode_selection_survives(self):
        step = self._step("Resolve the requested publish mode")
        self.assertIn("REQUESTED_TOKEN", step["run"])
        self.assertIn("use_token_fallback", step["env"]["REQUESTED_TOKEN"])

    def test_oidc_publish_keeps_provenance(self):
        step = self._step("Publish with OIDC Trusted Publishing")
        self.assertIn("--provenance", step["run"])
        self.assertNotIn("NODE_AUTH_TOKEN", step.get("env", {}))

    def test_token_publish_omits_provenance(self):
        step = self._step("Publish with NPM_TOKEN (deliberate opt-in, no provenance)")
        self.assertNotIn("--provenance", step["run"], "a classic token cannot attest")
        self.assertIn("NODE_AUTH_TOKEN", step["env"])

    def test_publish_steps_are_mutually_exclusive(self):
        oidc = self._step("Publish with OIDC Trusted Publishing")
        token = self._step("Publish with NPM_TOKEN (deliberate opt-in, no provenance)")
        self.assertEqual(oidc["if"], "steps.mode.outputs.requested == 'trusted'")
        self.assertEqual(token["if"], "steps.mode.outputs.requested == 'token'")

    def test_fail_closed_upload_check_survives(self):
        step = self._step("Require a successful upload")
        body = step["run"]
        self.assertIn("TRUSTED_OUTCOME", step["env"])
        self.assertIn("TOKEN_OUTCOME", step["env"])
        self.assertIn("npm Trusted Publishing failed", body)
        self.assertIn("deliberate NPM_TOKEN mode", body)

    def test_version_existence_gate_survives(self):
        step = self._step("Check the version is not already published")
        self.assertIn("already published to npm", step["run"])

    def test_attestation_verification_survives(self):
        step = self._step("Verify the default publish is attested")
        self.assertEqual(step["if"], "steps.trusted.outcome == 'success'")
        self.assertIn("npm/v1/attestations/", step["run"])

    def test_registry_visibility_check_survives(self):
        step = self._step("Verify the published version")
        self.assertIn("npm view", step["run"])

    def test_no_continue_on_error_anywhere(self):
        self.assertNotIn("continue-on-error", self.text)

    def test_least_privilege_and_environment(self):
        self.assertEqual(self.job["permissions"], {"id-token": "write", "contents": "read"})
        self.assertEqual(self.job["environment"], "npm")

    def test_triggers_are_push_and_dispatch_only(self):
        # PyYAML parses the bare key `on` as the boolean True.
        triggers = self.document[True] if True in self.document else self.document["on"]
        self.assertEqual(sorted(triggers), ["push", "workflow_dispatch"])

    # -- behaviour trace -----------------------------------------------------
    def _run_mode_step(self, requested: str, token: str) -> tuple[int, str, str]:
        """Execute the mode-resolution step as bash and capture its decision.

        Returns ``(returncode, combined_output, mode)``. stdout and stderr are
        combined because GitHub Actions emits ``::warning::`` and ``::error::``
        annotations on stderr; the step's decision line goes to ``$GITHUB_OUTPUT``.
        """
        # Never call bare `bash` here. On a Windows runner that resolves to the
        # WSL launcher stub, which fails for every input, so these tests would
        # report the mode logic as broken when only the shell is.
        shell = checker.usable_bash()
        if shell is None:
            self.skipTest("no working bash on this platform")

        body = self._step("Resolve the requested publish mode")["run"]

        # `mktemp` with no template honours TMPDIR, so the file never lands in
        # the repository root. bash deletes it itself afterwards: a path handed
        # back to Python on Windows would not survive the trip, and a scratch
        # directory used as the child's cwd stays locked after it exits.
        prelude = (
            "#!/usr/bin/env bash\n"
            'GITHUB_OUTPUT="$(mktemp)"\n'
            'export GITHUB_OUTPUT\n'
            f"export REQUESTED_TOKEN='{requested}'\n"
            f"export NPM_TOKEN='{token}'\n"
        )
        # Print the decision line, then remove the scratch file whatever happened.
        footer = (
            '\necho "MODE-BEGIN"\n'
            'cat "$GITHUB_OUTPUT" 2>/dev/null || true\n'
            'echo "MODE-END"\n'
            'rm -f "$GITHUB_OUTPUT"\n'
        )
        proc = subprocess.run(
            [shell, "-s"],
            input=(prelude + body + footer).encode("utf-8"),
            capture_output=True,
            check=False,
        )
        text = (
            proc.stdout.decode("utf-8", "replace") + proc.stderr.decode("utf-8", "replace")
        ).replace("\ufffd", "")
        mode = ""
        lines = text.splitlines()
        try:
            start = lines.index("MODE-BEGIN") + 1
            end = lines.index("MODE-END")
        except ValueError:  # pragma: no cover - only if the step exits early
            start, end = 0, 0
        for line in lines[start:end]:
            if line.strip().startswith("requested="):
                mode = line.strip()
        annotations = "\n".join(
            line for line in text.splitlines() if line.strip().startswith("::")
        )
        return proc.returncode, annotations or text, mode

    def test_push_trigger_resolves_to_oidc(self):
        """A push has no dispatch input, so the empty value must mean OIDC."""
        rc, output, mode = self._run_mode_step("", "")
        self.assertEqual(rc, 0, output)
        self.assertEqual(mode, "requested=trusted")
        self.assertNotIn("::warning::", output, "a push must not warn about tokens")

    def test_dispatch_without_opt_in_resolves_to_oidc(self):
        rc, output, mode = self._run_mode_step("false", "")
        self.assertEqual(rc, 0, output)
        self.assertEqual(mode, "requested=trusted")

    def test_dispatch_with_token_present_still_resolves_to_oidc(self):
        """A stale secret must not downgrade the publish."""
        rc, output, mode = self._run_mode_step("false", "an-existing-secret")
        self.assertEqual(rc, 0, output)
        self.assertEqual(mode, "requested=trusted")
        self.assertNotIn("::warning::", output)

    def test_dispatch_with_opt_in_resolves_to_token_and_warns(self):
        rc, output, mode = self._run_mode_step("true", "an-existing-secret")
        self.assertEqual(rc, 0, output)
        self.assertEqual(mode, "requested=token")
        self.assertIn("::warning::", output)
        self.assertIn("NOT be provenance-signed", output)

    def test_opt_in_without_a_credential_fails_closed(self):
        rc, output, mode = self._run_mode_step("true", "")
        self.assertNotEqual(rc, 0, "an opt-in with no secret must not proceed")
        self.assertIn("::error::", output)
        self.assertEqual(mode, "", "no mode may be emitted when it fails")

    def test_non_boolean_input_fails_closed(self):
        rc, output, _ = self._run_mode_step("maybe", "an-existing-secret")
        self.assertNotEqual(rc, 0)
        self.assertIn("must be a boolean", output)


if __name__ == "__main__":
    unittest.main()