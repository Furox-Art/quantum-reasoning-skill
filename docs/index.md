# Quantum Reasoning Skill — documentation

Start here, then pick the depth you need.

## First steps

1. [Getting started](getting-started.md) — what the skill is, how to install it, and the
   first prompt to try.
2. [Quickstart](quickstart.md) — a runnable verification script, its verified output, and
   the provenance of every number it prints.
3. [Skill contract](../SKILL.md) — the normative protocol. If the skill and a doc disagree,
   `SKILL.md` wins.

## Protocol and implementation

| Document | What it answers |
| --- | --- |
| [Skill contract](../SKILL.md) | What the model must do, when, and what it must never claim |
| [Measurement methodology](MEASUREMENT.md) | The exact formulas, weights and thresholds behind the reference controller |
| [Host compatibility](COMPATIBILITY.md) | Which host capabilities are required, expressed as capabilities rather than vendors |
| [Branch controller](../reference/branch_controller.py) | The reference implementation of scoring, dormancy, revival and collapse |

## Examples

| Document | What it shows |
| --- | --- |
| [Usage examples](../examples/usage.md) | Prompt shapes for scientific, mathematical, debugging and planning tasks |
| [Host integration](../examples/host-integration.md) | Native skill directory, persistent-instruction wrapper, controller-assisted agent, benchmark A/B setup |

## Benchmarks

| Document | What it shows |
| --- | --- |
| [Benchmark protocol](../benchmark/README.md) | Cases, schemas, evaluator, controls, submission rules |
| [Seed cases](../benchmark/cases.jsonl) | Six deterministic smoke-test cases |

**No baseline-versus-skill model evaluation has been published.** The seed cases prove the
harness runs; they are not evidence that this skill improves reasoning. Every contributed
number must ship the provenance listed in
[CONTRIBUTING.md](../CONTRIBUTING.md#benchmark-provenance-requirements).

## Project governance

| Document | Purpose |
| --- | --- |
| [Contributing](../CONTRIBUTING.md) | How to propose a change and how to submit benchmark results |
| [Code of conduct](../CODE_OF_CONDUCT.md) | Expected behaviour in issues, pull requests and discussions |
| [Security policy](../SECURITY.md) | How to report a vulnerability, and what is in scope |
| [Changelog](../CHANGELOG.md) | Release history |
| [Citation metadata](../CITATION.cff) | How to cite this protocol and software |
| [License](../LICENSE) | MIT |

## Reporting problems

- Bug or defect: [Bug report](https://github.com/Furox-Art/quantum-reasoning-skill/issues/new?template=bug-report.yml)
- Feature idea: [Feature request](https://github.com/Furox-Art/quantum-reasoning-skill/issues/new?template=feature-request.yml)
- Question or unclear documentation: [Question](https://github.com/Furox-Art/quantum-reasoning-skill/issues/new?template=question.yml)
- Benchmark submission: [Benchmark result](https://github.com/Furox-Art/quantum-reasoning-skill/issues/new?template=benchmark-result.yml)
- Vulnerability: do **not** open a public issue with details. See [SECURITY.md](../SECURITY.md).