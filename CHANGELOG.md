# Changelog

All notable changes to this project are documented here.

## [Unreleased]

### Fixed

- `twine` is pinned to `7.0.0` instead of `6.1.0` in every workflow that runs
  `twine check`. The 6.x line hardcodes a metadata-version list ending at `2.4`
  in `twine/package.py`, replacing the list `packaging` would supply, so
  `twine check --strict` rejects a valid artifact whose build backend emits
  `Metadata-Version: 2.5` with
  `InvalidDistribution: '2.5' is not a valid metadata version`. The repository was
  not broken *today* because `hatchling 1.27.0` emits `2.4`, but the pins were one
  dependency bump away from breaking the next release.
- `hatchling` moves `1.27.0` → `1.32.4`, which emits `Metadata-Version: 2.5`. This
  is the version the previous pair could not validate, so the backend and the
  validator moved together. The wheel and sdist file sets are byte-identical to
  the 1.32.4-independent 1.1.1 build apart from the metadata version, the
  `Generator` line and `RECORD`.

### Added

- `bin/check_toolchain_pins.py` asserts the *relationship* between the `twine` pin
  and the build-backend pin rather than either value alone: every workflow
  running `twine check` must pin twine, must pin it at or above `7.0.0`, and
  `UNPINNED` is treated as a failure. `pyproject.toml` and `constraints.txt` are
  checked against the workflows. Wired into the `build distributions` job using
  the metadata version read from the artifact that job just built, so the guard
  is anchored to what is actually emitted rather than to a hardcoded expectation.

No version bump: 1.1.1 is already published and the artifact contents are
unchanged by this fix. The point is to keep the *next* release from failing.

## [1.1.1] - 2026-10-04

Documentation corrections plus one workflow fix. This release exists primarily so
that the PyPI project page picks up the corrected `README.md`: the README is the
distribution long description, so only a new release can change it.

The PyPI 1.1.0 long description still advertised `from quantum_reasoning_skill
import ReasoningSession` and a `session.collapse()` API that has never existed in
this codebase, plus an "npm is no longer published" claim contradicted by the
README's own npm badge and install command. All of that is now removed.

Packaging and security hardening that landed after 1.1.0 also ships in this
release, since 1.1.0 was built before those commits existed:

- Benchmark import boundaries and path guards, plus the no-dynamic-eval and
  import-hardening tests, are included for the first time. The 1.1.0 sdist
  contains none of these files.
- `publish-release` now polls for required checks instead of refusing a green
  commit on first glance, and release automation no longer uses `workflow_run`.
- npm publishing was re-enabled on OIDC Trusted Publishing with provenance;
  publishing with `NPM_TOKEN` is a deliberate opt-in and is never
  provenance-signed.

### Fixed

- README claimed "npm is no longer published". npm `quantum-reasoning-skill@1.1.0` is
  published and the channel is live; the claim also contradicted the README's own npm
  badge, install command, `npx` example and distribution table. Removed.
- README documented a `--path` flag for the `quantum-reasoning` console script. It does
  not exist there — the command exits `2` with `unrecognized arguments: --path`. `--path`
  belongs to the npm `index.js` CLI only. The distribution surface table is split by owner,
  and `docs/getting-started.md` no longer implies otherwise.
- README said "three verified paths reach `SKILL.md`" and then showed two.
- README said all three channels were verified by CI while its own table left the
  `git clone` row unverified. Restated to what is actually checked: both packaged artifacts.
- README described the release gate's negative-control mode as removing "each installed
  asset". It covers four scenarios and never exercises `VERSION` or the console entry point.
- The quickstart output pasted into `README.md` and `docs/quickstart.md` cited commit
  `6bd9c9b`, which is not an ancestor of `main` and is not a valid object in this
  repository, so no reader could obtain it. It also reported the `SKILL.md` digest as
  7145 → `a63dd273` only by coincidence of a CRLF checkout; the git blob is
  7145 bytes / `sha256:bd70f42ce11d1713`, which is what CI and every Linux and macOS user
  sees. Both the digest and the commit citation are corrected, and the duplicated block
  was removed from the README in favour of a link so it cannot drift again.
- npm publishing with `NPM_TOKEN` no longer passes `--provenance`. A classic
  long-lived token cannot mint a Sigstore attestation, so the flag made npm
  attempt an attestation it could not produce. Provenance remains on the OIDC
  Trusted Publishing path only.
- The npm Trusted Publishing version gate is now a numeric semver comparison
  instead of the pattern `^11\.(5[1-9]|[6-9][0-9])\.|^1[2-9]\.`, which wrongly
  rejected legitimate versions including npm 11.9.0 and 11.19.0.
- The `publish-release` workflow no longer fails on green commits. Its `verify`
  job queried the required check runs exactly once, saw `pending` while the
  validation workflow was still starting, and refused to tag. It now polls with a
  bounded 5-minute deadline and refuses only on a genuine `failure`,
  `cancelled`, `timed_out`, or a check that never reaches a terminal state.

### Changed

- Publishing with `NPM_TOKEN` is now a deliberate opt-in via the
  `use_token_fallback` `workflow_dispatch` input (boolean, default `false`)
  instead of an automatic fallback triggered by the mere presence of the secret.
  A stale secret can no longer silently downgrade a publish. The requested mode
  fails closed when its credential is absent.

- npm is a supported distribution channel again and `npm publish` is
  re-enabled. Trusted Publishing via OIDC is the primary credential path, and is
  the only automatic one.
  No version bump is included: the published 1.1.0 tarball was verified healthy
  (`require()` and `npx quantum-reasoning --validate` both succeed).

- README is 246 → 180 lines after deleting a 50-line output block that was
  byte-identical to the one in `docs/quickstart.md`, and sections that restated
  `SKILL.md` verbatim. No coverage was lost: the frozen release contract, the
  reference-controller API, the benchmark harness's scripts and schemas, and the
  test and CI story were added in the space reclaimed.

### Added

- README now documents the frozen release contract: twelve public names in
  `reference/branch_controller.py` are asserted by
  `bin/check_release_contract.py`, and renaming any one of them halts the release.
  `WEIGHTS` is deliberately excluded so the scoring model can change freely.
- README now lists every public reference-controller function and type, rather than
  naming one of seventeen.
- README now names `benchmark/validate_submission.py`, `benchmark/paths.py`, the four
  JSON Schemas, and shows a real `benchmark/evaluate.py` invocation with its
  `--cases-dir` and `--max-bytes` confinement.
- README now states the test and CI surface: 1,575 of 3,635 Python lines across
  9 test modules, on `unittest`, Python 3.10–3.14, Linux/Windows/macOS, with the
  toolchain double-pinned in `pyproject.toml` and `constraints.txt`.
- README and `CONTRIBUTING.md` now mention `codemeta.json`, the five issue templates
  and the pull-request template.
- `CONTRIBUTING.md` gained `Toolchain pinning` and `Release version` sections, which
  the README links to by anchor.

## [1.1.0] - 2026-10-02

### Fixed

- The published wheel is no longer an empty shell: `SKILL.md`, `VERSION`,
  `reference/`, `benchmark/`, `docs/` and `examples/` now ship inside the
  distribution instead of only in the source tree.
- The npm entry point no longer executes `SKILL.md` as JavaScript. `require()`,
  `bin/quantum-reasoning` and `npm test` all work; the previous version threw a
  `SyntaxError` on any import.
- The npm tarball no longer ships `.github/`, `tests/` and `pyproject.toml`.
- Version drift is removed. `VERSION`, `pyproject.toml`, `package.json`,
  `CITATION.cff`, `CHANGELOG.md` and the installed metadata are now asserted to
  be identical by CI.

### Fixed

- `benchmark/validate_submission.py` used a bare `import evaluate`, which only
  resolved when the script's own directory happened to be on `sys.path`.
  `python -m benchmark.validate_submission` failed with `ModuleNotFoundError`;
  both invocations now work.

### Added

- `bin/quantum-reasoning` console script that validates the packaged skill
  contract, installable via `pip install quantum-reasoning-skill`.
- A release contract gate that installs the built wheel and fails the release
  unless the skill contract ships in the distribution, the documented console
  entry point runs, and the reference branch controller imports and is callable.
  A negative control proves the gate fails when an installed asset is removed.
- CI jobs for lint (`ruff`), type checking (`mypy --strict`) and coverage with a
  ratcheting threshold.
- CI build job that runs `python -m build` and `twine check` on every change.
- CI job that installs the built wheel and verifies the skill contract, so the
  distribution is validated as a consumer would see it.

### Changed

- Release automation no longer uses `workflow_run`. Privileged publishing is
  gated on `push` to the default branch with no write permissions on
  untrusted events.
- Actions are pinned to full commit SHAs, workflow permissions are least
  privilege, and `continue-on-error` was removed from publish steps.
- Branch protection on `main` requires these six check contexts before a push
  can land: `repository contract`, `lint`, `types`, `coverage`,
  `build distributions`, `installed API contract`. It also blocks force-push,
  branch deletion and non-linear history, and applies to administrators.
  Separately, ruleset `main-protection` (id `24343853`) blocks deletion and
  force-push with no bypass actors. Required status checks are enforced by
  branch protection, **not** by the ruleset: `required_status_checks` could not
  be added to the ruleset through the API on this plan, and neither could
  `required_pull_request`. Direct pushes to `main` are therefore still
  permitted as long as the six checks pass. This is a known gap.
- Python CI matrix covers 3.10 through 3.14 on Linux plus a Windows job.

## [0.3.1] - 2026-09-07

### Added

- Community benchmark contribution policy in `CONTRIBUTING.md`.
- GitHub **Benchmark result**, **Bug report**, and **Feature request** issue forms.
- Pull-request checklist for tests, documentation, benchmark integrity, and sensitive-data hygiene.
- Draft 2020-12 JSON Schemas for benchmark cases, result rows, experiment metadata, and comparison output.
- `benchmark/validate_submission.py` for machine-validating reproducible community benchmark bundles.
- Tests that reject missing benchmark artifacts, tampered comparisons, and incomplete integrity metadata.
- Capability-based host compatibility contract in `docs/COMPATIBILITY.md`.
- Generic native-skill, persistent-instruction, and controller-assisted integration examples.
- `SECURITY.md` vulnerability-reporting policy.
- `CITATION.cff` research-software citation metadata.

### Changed

- Benchmark documentation now explicitly assigns real-model evaluation to users and contributors rather than requiring maintainer-run access to every model/provider.
- Community benchmark PRs now include the exact `cases.jsonl` used and are re-evaluated by CI from their raw baseline/skill files.
- Third-party benchmark submissions are treated as reproducible external measurements, not automatic project endorsements or universal performance claims.
- Release publishing now runs only after `validate-skill` succeeds on `main`; a failed validation cannot publish a release.
- GitHub Actions dependencies are pinned to exact commit SHAs and CI enforces future pinning.
- CI now validates schemas, version/citation consistency, host/documentation links, and community result bundles.

## [0.3.0] - 2026-09-07

### Added

- Deterministic reference branch controller with explicit scoring and state transitions.
- Shared-assumption and semantic-correlation penalty.
- Quantified dormant/rejected state rules and branch revival triggers.
- Uncertainty-based recommended search width.
- Explicit collapse criteria and leader-margin checks.
- Measurement specification documenting formulas and calibration requirements.
- Reproducible baseline-vs-skill benchmark protocol.
- Seed benchmark cases and JSONL result schema.
- Benchmark evaluator for accuracy, token/tool cost, latency, branch diversity, error recovery and contradiction resolution.
- Behavioral unit tests for the branch controller and benchmark evaluator.
- CI checks for Python compilation, benchmark schema validation and behavioral tests.
- Automated GitHub tag and Release publishing driven by the `VERSION` file.

### Changed

- `SKILL.md` now distinguishes qualitative protocol rules from unvalidated reference thresholds.
- `README.md` now documents the measurable framework and makes clear that empirical performance improvement has not yet been demonstrated.
