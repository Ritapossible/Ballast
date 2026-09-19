"""How big the test suite is, counted rather than remembered.

`report._red_team_count` already existed because the evidence page once claimed 18
red-team tests against a file holding 25 - seven were added the day the executor
boundary was closed, which is exactly when the number mattered most and was least
likely to be reread. The lesson was learned in one place and three literals
survived it: the evidence page said "Eighteen", the docs page said "18", and
docs/SUBMISSION.md - the document a judge reads end to end - claimed 79 tests in
one sentence and 103 in another while the suite held 347.

Every measured number in this project is generated and guarded. Prose about those
numbers was not, which is how all three went stale silently. So the counts live
here, the pages call them, and tests/test_submission_figures.py fails when the
prose disagrees.
"""
from __future__ import annotations

import re
from pathlib import Path

from . import config

TESTS = config.ROOT / "tests"

# A method definition, not every occurrence of the characters. Counting the bare
# substring reported 352 against a suite unittest ran as 351, because a test that
# asserts on `count("def test_")` contains the string it counts. One off is still
# a number in the submission document that disagrees with the command printed
# beside it.
_DEF = re.compile(r"^[ \t]*def (test_\w+)\s*\(", re.M)


def _count(path: Path) -> int:
    try:
        return len(_DEF.findall(path.read_text()))
    except OSError:
        return 0


def red_team() -> int:
    """Hostile intents driven at the enforcer."""
    return _count(TESTS / "test_enforcer.py")


def end_to_end() -> int:
    """Tests that run the real night/morning path against a throwaway ledger."""
    return _count(TESTS / "test_integration.py")


def total() -> int:
    try:
        return sum(_count(p) for p in sorted(TESTS.glob("test_*.py")))
    except OSError:
        return 0
