# Changelog

All notable changes to this project are documented here.

## [Unreleased]

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
- `main` is protected by a ruleset requiring a passing `validate-skill` check
  and a pull request.
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
