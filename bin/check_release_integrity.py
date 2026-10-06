#!/usr/bin/env python3
"""Release-publish integrity guard.

Checks that the facts this repository asserts about its own published releases are
still true, and that the release path cannot silently claim an attestation it did
not produce.

Background
----------
``1.1.1`` went out on npm with no Sigstore provenance attestation because it was
published through the ``NPM_TOKEN`` opt-in path rather than OIDC Trusted
Publishing. The package itself was fine; only the provenance record was missing,
and attestations are bound to a publish event so they cannot be backfilled. Two
things follow, and both are easy to get wrong afterwards:

* a documentation claim that ``1.1.1`` is attested would be false;
* a future release must not reach the registry through the token path by accident.

This guard is deliberately offline. It asserts *documentary consistency* — that the
repository says the same thing everywhere, and that no document claims an
attestation for a version the registry does not carry. The attested version set is
passed in explicitly rather than fetched, so the check is deterministic and does
not depend on registry availability.

Use ``--attested-npm`` to record what the registry actually reports.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

#: npm versions the registry reports as carrying an attestation.
KNOWN_ATTESTED_NPM = frozenset({"1.1.0"})

#: npm versions the registry reports as having no attestation.
KNOWN_UNATTESTED_NPM = frozenset({"1.0.0", "1.1.1"})

#: Every release this package has published to npm. Used by the registry-supplied
#: check, which must reason about any of these rather than only the ones whose
#: status happens to be recorded below.
RELEASED_NPM_VERSIONS = frozenset({"1.0.0", "1.1.0", "1.1.1"})

#: A release-version token.
VERSION_TOKEN = re.compile(r"\b1\.\d+\.\d+\b")

#: Any mention of an attestation, in any inflection. "is attested" is just as much
#: a claim as "carries an attestation", so it must be in scope.
ATTESTATION_MENTION = re.compile(r"attest(?:ed|ing|ation|ations|e)", re.IGNORECASE)

#: Wording that would assert an attestation for a release.
ATTESTATION_CLAIM = re.compile(
    r"(?:is|are|carries|carry|has|have|with|holds?)\s+"
    r"(?:a\s+)?(?:real\s+|valid\s+|signed\s+)?"
    r"(?:sigstore\s+|slsa\s+|pep\s*740\s+)?"
    r"(?:provenance\s+)?(?:attestation|attestations)",
    re.IGNORECASE,
)

#: Wording that negates or qualifies an attestation claim.
NEGATION = re.compile(
    r"\b(?:no|not|never|cannot|without|neither|nor|unattested|missing|absent)\b",
    re.IGNORECASE,
)


def doc_files() -> list[Path]:
    """Every markdown file permitted to make supply-chain claims."""
    paths = [ROOT / "README.md", ROOT / "SECURITY.md", ROOT / "CHANGELOG.md"]
    paths.extend(sorted((ROOT / "docs").rglob("*.md")))
    return [path for path in paths if path.is_file()]


def version_mentions(text: str) -> set[str]:
    return set(VERSION_TOKEN.findall(text))


def sentences(text: str) -> list[str]:
    """Split prose into sentences.

    Sentence boundaries matter: a claim about one release routinely sits next to a
    disclosure about another ("use 1.1.0, which carries an attestation. Do not
    treat the absence of an attestation on 1.1.1 as evidence of tampering.").
    Scanning across that boundary reads the first clause as a claim about the
    second release.
    """
    chunks: list[str] = []
    for block in text.split("\n"):
        stripped = block.strip()
        if stripped:
            chunks.extend(part for part in re.split(r"(?<=[.!?:])\s+", stripped) if part)
    return chunks


def is_prose(chunk: str) -> bool:
    """True when a chunk reads as prose rather than a probe or a code listing."""
    if "curl" in chunk or "http" in chunk:
        return False
    return not chunk.strip().startswith("`")


#: An affirmative claim bound to a version, e.g. "1.1.1 is attested" or
#: "1.1.1 carries a Sigstore provenance attestation". Deliberately narrow: a bare
#: negation elsewhere in the paragraph must not excuse a real claim, and a real
#: claim must not be excused by a negation that belongs to another sentence.
TIGHT_CLAIM = re.compile(
    # "is attested" / "was signed" — the bare adjectival form, with no noun.
    r"\b(?:is|are|was|were|been)\s+"
    r"(?:genuinely\s+|actually\s+|cryptographically\s+)?"
    r"(?:sigstore[-\s]?|slsa[-\s]?|pep\s*740[-\s]?)?"
    r"(?:provenance[-\s]?)?"
    r"(?:attested|verified|verified-signed)\b"
    # "... carries/holds a Sigstore provenance attestation"
    r"|\b(?:carries|carry|carried|has|have|had|with|holds?|held|includes?|included)\s+"
    r"(?:a\s+|an\s+|the\s+|its\s+|their\s+)?"
    r"(?:real\s+|valid\s+|signed\s+|genuine\s+|full\s+)?"
    r"(?:sigstore\s+|slsa\s+|pep\s*740\s+)?"
    r"(?:provenance\s+|build\s+|supply[-\s]chain\s+)?"
    r"attestations?",
    re.IGNORECASE,
)

#: The affirmative marker used in an attestation-status table cell.
TABLE_AFFIRMATIVE = re.compile(r"^\**\s*(?:yes|y|true|attested|signed)\b", re.IGNORECASE)


def mentions(text: str) -> list[str]:
    """Every sentence that mentions an attestation."""
    return [sentence for sentence in sentences(text) if ATTESTATION_MENTION.search(sentence)]


def table_row_claims_attestation(window: str, unattested: set[str]) -> bool:
    """True when a table row marks an unattested version as attested.

    In a table the affirmative signal is a ``yes`` cell rather than a verb, so the
    prose rule cannot see it.
    """
    for line in window.splitlines():
        if "|" not in line:
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if not any(ATTESTATION_MENTION.search(cell) for cell in cells):
            continue
        if not any(set(VERSION_TOKEN.findall(cell)) & unattested for cell in cells):
            continue
        if any(TABLE_AFFIRMATIVE.match(cell) for cell in cells):
            return True
    return False


def check_no_unattested_version_claimed() -> list[str]:
    """No document may assert an attestation for a version the registry lacks."""
    problems: list[str] = []
    for path in doc_files():
        text = path.read_text(encoding="utf-8")
        relative = path.relative_to(ROOT)
        for span in mentions(text):
            if not is_prose(span):
                continue
            unattested = version_mentions(span) & KNOWN_UNATTESTED_NPM
            if not unattested:
                continue
            # A denial *bound to the attestation* excuses the span; a stray
            # negation elsewhere in it does not. "carries no attestation" is a
            # disclosure, "is no exception: it carries an attestation" is a claim.
            if TIGHT_DENIAL.search(span):
                continue
            if TIGHT_CLAIM.search(span) or table_row_claims_attestation(span, unattested):
                problems.append(
                    f"{relative}: asserts an attestation for a version the registry "
                    f"does not carry ({', '.join(sorted(unattested))}): "
                    f"{' '.join(span.split())[:150]!r}"
                )
    return problems


#: A disclosure bound tightly to the attestation itself, e.g. "carries no
#: attestation", "not attested", "without provenance", "unattested". A bare "no"
#: elsewhere in the sentence is deliberately not enough: "1.1.1 is no exception:
#: it carries an attestation" is a claim, not a disclosure.
TIGHT_DENIAL = re.compile(
    r"(?:carries|carried|has|have|with|is|are|was|were)\s+"
    r"(?:a\s+|an\s+|any\s+|its\s+|their\s+)?"
    r"(?:sigstore\s+|slsa\s+|pep\s*740\s+)?"
    r"(?:provenance\s+|build\s+|supply[-\s]chain\s+)?"
    r"(?:attestations?|provenances?)\s+"
    r"(?:is\s+|are\s+)?(?:absent|missing|nil|none)"
    r"|(?:carries|carried|has|have|with|is|are|was|were)\s+"
    r"(?:a\s+|an\s+|any\s+|its\s+|their\s+)?"
    r"(?:sigstore\s+|slsa\s+|pep\s*740\s+)?"
    r"(?:provenance\s+|build\s+|supply[-\s]chain\s+)?"
    r"(?:no|not|never)\s+"
    r"(?:sigstore\s+|slsa\s+|pep\s*740\s+)?"
    r"(?:provenance\s+|build\s+|supply[-\s]chain\s+)?"
    r"attestations?"
    r"|\bunattested\b"
    r"|\bnot\s+attested\b"
    r"|\bwithout\s+(?:an?\s+)?(?:sigstore\s+|slsa\s+|pep\s*740\s+)?"
    r"(?:provenance\s+|build\s+|supply[-\s]chain\s+)?attestations?",
    re.IGNORECASE,
)


def check_disclosures_match_the_registry(attested: frozenset[str]) -> list[str]:
    """A doc must not deny an attestation the registry actually reports.

    Guards the opposite drift: if npm later attests a release, documentation that
    still says it has none becomes false. Only a denial adjacent to the version
    counts, never a negation elsewhere in the same paragraph.
    """
    problems: list[str] = []
    for path in doc_files():
        text = path.read_text(encoding="utf-8")
        relative = path.relative_to(ROOT)
        for span in mentions(text):
            if not is_prose(span):
                continue
            denied = version_mentions(span) & attested
            if not denied:
                continue
            if not TIGHT_DENIAL.search(span):
                continue
            problems.append(
                f"{relative}: denies an attestation the registry reports for "
                f"{', '.join(sorted(denied))}: {' '.join(span.split())[:150]!r}"
            )
    return problems


def check_every_version_status_is_documented() -> list[str]:
    """Each known version's attestation status must be stated somewhere."""
    problems: list[str] = []
    corpus = "\n".join(path.read_text(encoding="utf-8") for path in doc_files())
    for version in sorted(KNOWN_ATTESTED_NPM | KNOWN_UNATTESTED_NPM):
        if version not in corpus:
            problems.append(
                f"no document mentions npm {version}; its attestation status is unstated"
            )
    return problems


def check_unattested_is_explicitly_disclosed() -> list[str]:
    """The unattested release must be named in a disclosure, not just omitted.

    Presence of the version string somewhere in the corpus is not enough: the
    disclosure has to sit in the same sentence as the attestation wording, and
    bound to the version the way TIGHT_DENIAL is.
    """
    for path in doc_files():
        text = path.read_text(encoding="utf-8")
        for chunk in sentences(text):
            for version in KNOWN_UNATTESTED_NPM:
                if version not in chunk:
                    continue
                if not ATTESTATION_MENTION.search(chunk):
                    continue
                if TIGHT_DENIAL.search(chunk) or table_denies_attestation(chunk, version):
                    return []
    return [
        "no document explicitly discloses that an npm release lacks an attestation; "
        "an unattested release must be stated, not merely omitted"
    ]


def table_denies_attestation(chunk: str, version: str = "") -> bool:
    """True when a status table marks a release as having no attestation.

    ``version`` narrows the check to a specific release when given; an empty
    string accepts any table row that carries a negative status cell.
    """
    if "|" not in chunk:
        return False
    cells = [cell.strip() for cell in chunk.strip().strip("|").split("|")]
    if version and version not in " ".join(cells):
        return False
    negative = re.compile(
        r"^\**\s*(?:no|not|none|n/?a|absent|missing|✗|❌|-)\s*\**$", re.IGNORECASE
    )
    return any(negative.match(cell) for cell in cells)


def check_claims_without_registry_support(attested: frozenset[str]) -> list[str]:
    """No document may claim an attestation the supplied registry set lacks.

    This is the live-data direction: CI passes whatever the npm attestations
    endpoint actually reports, so a document claiming provenance for a version the
    registry does not carry fails here. Using the injected set rather than the
    module constant is what makes this check meaningful when npm starts or stops
    attesting a release.
    """
    problems: list[str] = []
    for path in doc_files():
        text = path.read_text(encoding="utf-8")
        relative = path.relative_to(ROOT)
        for chunk in sentences(text):
            if not ATTESTATION_MENTION.search(chunk):
                continue
            if not is_prose(chunk):
                continue
            if TIGHT_DENIAL.search(chunk) or table_denies_attestation(chunk, ""):
                continue
            claimed = version_mentions(chunk) & RELEASED_NPM_VERSIONS
            if not claimed:
                continue
            if not TIGHT_CLAIM.search(chunk) and not table_row_claims_attestation(chunk, claimed):
                continue
            unsupported = claimed - attested
            if unsupported:
                problems.append(
                    f"{relative}: claims an attestation the registry does not report for "
                    f"{', '.join(sorted(unsupported))}: {' '.join(chunk.split())[:150]!r}"
                )
    return problems


def check_token_path_cannot_claim_provenance() -> list[str]:
    """Token publishing cannot claim provenance; auth is selected before upload."""
    problems: list[str] = []
    workflow = ROOT / ".github" / "workflows" / "npm-publish.yml"
    if not workflow.is_file():
        return ["npm-publish.yml is missing"]
    text = workflow.read_text(encoding="utf-8")

    if "Publish with NPM_TOKEN" not in text:
        problems.append("npm-publish.yml has no NPM_TOKEN publish step")
    else:
        body = text.split("Publish with NPM_TOKEN", 1)[1][:600]
        if "--provenance" in body:
            problems.append(
                "the NPM_TOKEN publish step passes --provenance; a classic token "
                "cannot mint a Sigstore attestation"
            )

    if "id-token: write" not in text:
        problems.append("npm-publish.yml does not request id-token: write")
    if "default: false" not in text:
        problems.append("use_token_fallback must default to false so OIDC is the default path")
    if "steps.mode.outputs.requested == 'trusted'" not in text:
        problems.append(
            "the OIDC publish step is not the default; expected "
            "steps.mode.outputs.requested == 'trusted'"
        )

    # Manual dispatches still honour the explicit checkbox. Automatic pushes may
    # select the already-proven NPM_TOKEN path when the secret exists, but that
    # decision must happen before either publish command starts. In particular,
    # a failed OIDC upload must never trigger a token retry.
    resolution = text.split("Resolve the requested publish mode")
    if len(resolution) < 2:
        problems.append("npm-publish.yml has no publish-mode resolution step")
    else:
        body = resolution[1][:2600]
        if "REQUESTED_TOKEN" not in body:
            problems.append(
                "the publish-mode resolution step does not read the use_token_fallback "
                "input for manual dispatches"
            )
        if "EVENT_NAME" not in body:
            problems.append(
                "the publish-mode resolution step does not distinguish automatic pushes "
                "from manual dispatches"
            )
        if not re.search(r'elif\s+\[\s+-n\s+"\$\{NPM_TOKEN:-\}"\s+\];\s+then', body):
            problems.append(
                "automatic pushes do not select the verified NPM_TOKEN path before publish"
            )

    token_publish = text.split("Publish with NPM_TOKEN", 1)
    if len(token_publish) == 2:
        token_head = token_publish[1][:500]
        if "trusted.outcome" in token_head or "trusted_publish.outcome" in token_head:
            problems.append(
                "the token publish step is keyed on an OIDC failure; credential selection "
                "must happen before publishing, not as a post-failure fallback"
            )
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="check_release_integrity",
        description=(
            "Assert the repository does not claim supply-chain attestations it does "
            "not have, and that the token publish path cannot fake one."
        ),
    )
    parser.add_argument(
        "--attested-npm",
        default=",".join(sorted(KNOWN_ATTESTED_NPM)),
        help="comma-separated npm versions the registry reports as attested",
    )
    args = parser.parse_args(argv)

    attested = frozenset(part.strip() for part in args.attested_npm.split(",") if part.strip())

    print(f"npm versions attested per registry : {', '.join(sorted(attested)) or 'none'}")
    print(f"npm versions known unattested     : {', '.join(sorted(KNOWN_UNATTESTED_NPM))}")
    print(f"documents inspected               : {len(doc_files())}")

    problems: list[str] = []
    problems.extend(check_no_unattested_version_claimed())
    problems.extend(check_disclosures_match_the_registry(attested))
    problems.extend(check_claims_without_registry_support(attested))
    problems.extend(check_every_version_status_is_documented())
    problems.extend(check_unattested_is_explicitly_disclosed())
    problems.extend(check_token_path_cannot_claim_provenance())

    if problems:
        print("\nrelease integrity contract FAILED:", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        return 1

    print(
        "release integrity contract satisfied: documentation matches the registry, "
        "and the token publish path cannot claim provenance."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
