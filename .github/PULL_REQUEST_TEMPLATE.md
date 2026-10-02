## Summary

Describe the change and the behavior it affects. Reference the issue it closes, if any.

## What changed for users

- [ ] No user-visible change (internal refactor, tests, CI)
- [ ] Documentation only
- [ ] Protocol or scoring behavior changed — see the benchmark-impact section below
- [ ] Host contract, schemas, or distribution changed

## Validation

The six required status checks on `main`:

- [ ] `python -m unittest discover -s tests -v`
- [ ] `ruff check .`
- [ ] `mypy`
- [ ] `python -m coverage run -m unittest discover -s tests && python -m coverage report`
- [ ] `python -m build --outdir dist && python -m twine check --strict dist/*`
- [ ] Installed API contract: install the built wheel and run `python bin/check_release_contract.py`

Also run `python docs/quickstart.py` if you changed anything a user runs.

- [ ] I added or updated tests when executable behavior changed
- [ ] I updated documentation when the public contract changed
- [ ] Every relative link in the documents I touched resolves
- [ ] `reference/branch_controller.py` weights and `docs/MEASUREMENT.md` still match, if I touched either
- [ ] `SKILL.md` still ships inside the distribution, if I touched packaging

## Claim accuracy

Required for any change that adds a number, a comparison, or an install path.

- [ ] Every number is either computed by a script in this repository or shipped with provenance: script and version, skill commit, provider and exact model version, run date, sampling parameters, repetitions, and platform
- [ ] Synthetic or placeholder output is labeled as such next to the number
- [ ] I did not add a performance claim that no measurement in this repository supports
- [ ] I did not describe a distribution channel (PyPI, npm) as an install path unless the published artifact contains what I claim it contains
- [ ] I did not document a Python API that does not exist; the real surface is the `quantum-reasoning` console script, the shipped asset, and `reference.branch_controller`
- [ ] I did not include secrets, credentials, private chain-of-thought, or fabricated benchmark telemetry

## Benchmark-impacting changes

If this changes `SKILL.md`, scoring, collapse/revival behavior, benchmark schemas, or
evaluation logic, explain how existing results should be interpreted and whether new
community runs are needed.