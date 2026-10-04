# Security policy

## Supported versions

Security fixes are applied to the current `main` branch and the latest published release.

## Reporting a vulnerability

**Do not open a public issue containing vulnerability details.** Not in the body, not in an
attachment, not in a linked gist or paste.

This repository does not publish a security contact address. To reach the maintainer
privately, use whichever channel is available to you:

1. **GitHub private reporting** — if this repository has GitHub's private vulnerability
   reporting enabled, use *Security* → *Report a vulnerability* on the Security tab. This
   opens a private advisory visible only to the maintainer and you.
2. **GitHub private message** — send a private message to the maintainer's GitHub profile
   asking for a private channel. Describe only the component and the rough impact.
3. **Public issue without details** — as a last resort, open an issue titled
   `Security: private contact requested`, stating only that you have a security report and
   asking for a private contact path. Do not describe the vulnerability, the affected file,
   or a proof of concept in that issue.

Include in the private report, when you can:

- the affected component and file paths;
- the `git commit` you tested (`git rev-parse HEAD`);
- reproduction steps or a proof of concept;
- the impact you believe it has, and any suggested mitigation.

## What to expect

- Acknowledgement of a valid report, and a fix or a documented decision not to fix.
- Credit in the release notes, if you want it.
- Please give maintainers reasonable time to publish a fix before disclosing publicly.

## Scope

Relevant reports include vulnerabilities in repository automation, benchmark ingestion and
validation, release workflows, or reference code that could cause untrusted contributed
content to execute unexpectedly, alter a published release, or expose secrets. The CI
supply chain — pinned GitHub Actions, PyPI trusted publishing, npm publish — is in scope.

## Supply-chain attestations

Not every published version carries a build attestation. This is a property of how
the artifact was published, not a defect in it:

| release | channel | attestation |
| --- | --- | --- |
| `1.1.0` | npm | yes — SLSA provenance + npm publish attestation (Sigstore) |
| `1.1.1` | npm | **no** — published via the long-lived-token path |
| `1.1.1` | PyPI | **no** — no PEP 740 attestation is produced for this upload |

Attestations are bound to a publish event and cannot be backfilled, so the gap on
`1.1.1` is permanent. The `1.1.1` artifacts are otherwise unchanged and pass the same
release contract as every other release.

Two things follow, and both matter when assessing a report:

- **A missing attestation is not itself a vulnerability.** It is expected for a
  token-published release. Do not file it as a supply-chain compromise.
- **An attestation is not a guarantee of correctness.** It proves the artifact was
  built by a named workflow in a named repository. It does not prove the build was
  correct or that the code is safe.

If you believe a published artifact was tampered with, that is in scope and worth
reporting — attach the version, the registry integrity hash, and how you obtained it.

Reasoning-quality disagreements and ordinary protocol bugs are **not** security
vulnerabilities. Use the [bug report](https://github.com/Furox-Art/quantum-reasoning-skill/issues/new?template=bug-report.yml)
form for those, and the
[Code of Conduct](CODE_OF_CONDUCT.md) for conduct concerns.