"""Atheris harness for the untrusted benchmark metadata validator."""

import json
import sys

import atheris

from quantum_reasoning_skill.benchmark.validate_submission import validate_metadata


def TestOneInput(data: bytes) -> None:
    fdp = atheris.FuzzedDataProvider(data)
    document = fdp.ConsumeUnicodeNoSurrogates(4096)
    try:
        validate_metadata(json.loads(document))
    except ValueError:
        return


atheris.Setup(sys.argv, TestOneInput)
atheris.Fuzz()
