# Changelog

All notable changes to this project are documented here.

## [Unreleased]

### Added

- Community benchmark contribution policy in `CONTRIBUTING.md`.
- GitHub **Benchmark result** issue template for independently run baseline-vs-skill evaluations.

### Changed

- Benchmark documentation now explicitly assigns real-model evaluation to users and contributors rather than requiring maintainer-run access to every model/provider.
- Third-party benchmark submissions are treated as reproducible external measurements, not automatic project endorsements or universal performance claims.

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
