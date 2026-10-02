# Getting started

## The problem

Ask a hard question and most assistants pick the first reasonable-sounding answer and then
defend it. That is pattern matching with confidence, not search.

## What this skill changes

It holds several competing answers open at once, attacks each one with evidence or tools,
and only settles when one is genuinely better supported. The branch bookkeeping is
explicit rather than hidden, so a host can measure it.

It is a **metaphor, not quantum computing.** It runs on ordinary models and ordinary
hardware; see [the README](../README.md#why).

## Step 1 — verify the checkout

```bash
git clone https://github.com/Furox-Art/quantum-reasoning-skill.git
cd quantum-reasoning-skill
python docs/quickstart.py
```

Requires Python 3.10+. Exit code `0` means the skill contract parses and the shipped
tooling runs. Full output and provenance: [Quickstart](quickstart.md).

**Install by cloning.** The published PyPI and npm packages do not currently ship
`SKILL.md`, so neither is an integration surface. The exact status of each channel is in
[the README distribution table](../README.md#distribution-status).

## Step 2 — install `SKILL.md` in your host

`SKILL.md` is the deliverable. It is a Markdown file with YAML front matter; keep the
front matter intact.

| Your host supports | Do this |
| --- | --- |
| A skill or plugin directory | Copy `SKILL.md` into that directory as the skill entry point |
| Persistent system or developer instructions | Load the whole file into that instruction layer before the task ([example](../examples/host-integration.md#2-persistent-instruction-wrapper)) |
| An explicit agent loop you control | Map observable branch measurements onto the reference controller ([example](../examples/host-integration.md#3-controller-assisted-agent)) |

Capability requirements in full: [Compatibility](COMPATIBILITY.md).

To check a copy landed correctly, keep the front matter and verify the two required fields:

```python
python -c "import pathlib;t=pathlib.Path('SKILL.md').read_text(encoding='utf-8');print('name: quantum-reasoning' in t);print('chars:',len(t))"
```

## Step 3 — ask a question worth branching over

```text
Should we migrate our monolith to microservices? Keep materially different migration
strategies open, say what evidence would refute each one, use whatever tools are
available to test them, and give me only the best-supported recommendation plus the
uncertainty that remains.
```

Good prompts name the branching behaviour you want, because not every host will infer it.
More shapes: [usage examples](../examples/usage.md).

## What you get

- Several genuinely different approaches explored, not paraphrases
- Each judged on evidence rather than plausibility
- Contradicted paths pruned; recoverable ones kept dormant and revived on new evidence
- A conclusion with the remaining uncertainty stated, and alternatives named if they
  genuinely survive

## When not to use it

Simple questions. If the answer is obvious, branching just burns tokens and latency.
`SKILL.md` scopes this: use it for difficult, ambiguous, multi-step or high-stakes
problems.

## What you do not get

A measured improvement. **No baseline-versus-skill evaluation has been published for this
repository**, and the reference thresholds are uncalibrated defaults. If you run the
evaluation yourself, [CONTRIBUTING.md](../CONTRIBUTING.md#benchmark-provenance-requirements)
lists the provenance every contributed number must carry.