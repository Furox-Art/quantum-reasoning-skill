# Changelog

All notable changes to this project are documented here.

## [Unreleased]

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
