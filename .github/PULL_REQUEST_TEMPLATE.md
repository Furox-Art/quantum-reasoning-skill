## Summary

Describe the change and the behavior it affects. Reference the issue it closes, if any.

## What changed for users

- [ ] No user-visible change (internal refactor, tests, CI)
- [ ] Documentation only
- [ ] Protocol or scoring behavior changed — see the benchmark-impact section below
- [ ] Host contract, schemas, or distribution changed

## Validation

- [ ] `python -m unittest discover -s tests -v`
- [ ] `python benchmark/evaluate.py --help`
- [ ] `python docs/quickstart.py`
- [ ] I added or updated tests when executable behavior changed
- [ ] I updated documentation when the public contract changed
- [ ] Every relative link in the documents I touched resolves
- [ ] `reference/branch_controller.py` weights and `docs/MEASUREMENT.md` still match, if I touched either

## Claim accuracy

Required for any change that adds a number, a comparison, or an install path.

- [ ] Every number is either computed by a script in this repository or shipped with provenance: script and version, skill commit, provider and exact model version, run date, sampling parameters, repetitions, and platform
- [ ] Synthetic or placeholder output is labeled as such next to the number
- [ ] I did not add a performance claim that no measurement in this repository supports
- [ ] I did not describe a distribution channel (PyPI, npm) as an install path unless the published artifact contains what I claim it contains
- [ ] I did not include secrets, credentials, private chain-of-thought, or fabricated benchmark telemetry

## Benchmark-impacting changes

If this changes `SKILL.md`, scoring, collapse/revival behavior, benchmark schemas, or
evaluation logic, explain how existing results should be interpreted and whether new
community runs are needed.