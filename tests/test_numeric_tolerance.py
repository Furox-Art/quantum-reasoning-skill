"""The one documented numeric tolerance, pinned at its boundary.

Why this exists
---------------
The suite's floats are floating-point arithmetic over committed artifacts that
round some values to six decimals, so ``assertEqual`` on floats rejects correct
artifacts and ``assertAlmostEqual``'s seven-decimal default is a second,
undocumented tolerance. The repository settled this with a single constant,
``conftest.NUMERIC_TOLERANCE``, plus the ``assert_close`` / ``is_close``
helpers that every comparison site uses; ``docs/MEASUREMENT.md`` carries the
rationale.

What was missing was a direct pin on the helper's decision boundary. The
artifact-level tests prove the tolerance absorbs *measured* drift, but nothing
failed if the boundary itself moved: a delta below the tolerance must pass and
a delta just above it must fail, at the exact value the constant names. These
tests also prevent the defect class from coming back -- a second tolerance
reappearing as ``assertAlmostEqual``, or the documented value drifting away
from the code -- without touching any comparison site.

No test performs a registry or network request, and none depends on the clock.
"""

from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import conftest  # noqa: E402  (repository root is on sys.path only after the insert)

TOLERANCE = conftest.NUMERIC_TOLERANCE


class ToleranceBoundaryTests(unittest.TestCase):
    """The boundary is the documented constant, on both sides of it."""

    def test_a_delta_below_tolerance_passes(self):
        conftest.assert_close(1.0, 1.0 + TOLERANCE / 2)

    def test_a_delta_just_above_tolerance_fails(self):
        with self.assertRaises(AssertionError):
            conftest.assert_close(1.0, 1.0 + TOLERANCE * 2)

    def test_the_boundary_itself_is_inclusive(self):
        """``<= tolerance`` is the documented contract, so the edge passes."""
        conftest.assert_close(1.0, 1.0 + TOLERANCE)

    def test_is_close_mirrors_assert_close_either_side_of_the_boundary(self):
        self.assertTrue(conftest.is_close(1.0, 1.0 + TOLERANCE / 2))
        self.assertFalse(conftest.is_close(1.0, 1.0 + TOLERANCE * 2))

    def test_the_failure_names_both_values_and_the_tolerance(self):
        with self.assertRaises(AssertionError) as ctx:
            conftest.assert_close(0.5, 0.75, message="mean tokens")
        message = str(ctx.exception)
        self.assertIn("0.5", message)
        self.assertIn("0.75", message)
        self.assertIn(f"{TOLERANCE:g}", message)
        self.assertIn("mean tokens", message)

    def test_absent_measurements_only_agree_with_each_other(self):
        """``None`` means "not measured"; it never agrees with a number."""
        self.assertTrue(conftest.is_close(None, None))
        self.assertFalse(conftest.is_close(None, 0.0))
        self.assertFalse(conftest.is_close(0.0, None))
        with self.assertRaises(AssertionError):
            conftest.assert_close(None, 1.0)


class SingleToleranceGuardTests(unittest.TestCase):
    """No second, undocumented tolerance may reappear anywhere in the suite."""

    #: The *call*, not the word: several documents explain in prose why this
    #: method is not used, and quoting the reason is not using it.
    ALMOST_EQUAL_CALL = re.compile(r"\.assertAlmostEqual\s*\(")

    def test_no_assert_almost_equal_call_in_any_source(self):
        offenders = []
        for path in sorted(ROOT.rglob("*.py")):
            if {"__pycache__", ".git"} & set(path.relative_to(ROOT).parts):
                continue
            if self.ALMOST_EQUAL_CALL.search(path.read_text(encoding="utf-8")):
                offenders.append(path.relative_to(ROOT).as_posix())
        self.assertEqual(
            offenders,
            [],
            "assertAlmostEqual's seven-decimal default is a second tolerance; "
            "use conftest.assert_close",
        )

    def test_the_documented_value_matches_the_code(self):
        """docs/MEASUREMENT.md must state the constant the code actually uses."""
        self.assertEqual(TOLERANCE, 1e-6)
        text = (ROOT / "docs" / "MEASUREMENT.md").read_text(encoding="utf-8")
        self.assertIn("conftest.NUMERIC_TOLERANCE = 1e-6", text)

    def test_every_helper_defaults_to_the_documented_tolerance(self):
        import inspect

        for helper in (conftest.is_close, conftest.assert_close):
            signature = inspect.signature(helper)
            self.assertEqual(
                signature.parameters["tolerance"].default,
                TOLERANCE,
                f"{helper.__name__} defaults to a different tolerance",
            )


if __name__ == "__main__":
    unittest.main()
