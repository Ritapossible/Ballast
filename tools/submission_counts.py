"""Regenerate the repo-describing counts in docs/SUBMISSION.md.

    python3 tools/submission_counts.py           # rewrite them
    python3 tools/submission_counts.py --check   # fail if stale (CI runs this)

SUBMISSION.md is the document a judge reads end to end, and it described this repo
with four numbers nobody generated: 18 red-team tests against a file holding 25, 79
tests in one sentence and 103 in another against a suite of 347, and 17
documentation sections against 19. `ballast/report.py` already counted the
red-team suite for the same reason - the lesson was applied to one call site and
three prose literals survived it.

The prose here is argued, so it is not generated wholesale. These counts are, for
the same reason the README's measured block is: a number that only changes when
somebody remembers to change it is a number that goes wrong silently, and this one
goes wrong in the direction of overclaiming rigour.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ballast import suite

ROOT = Path(__file__).resolve().parent.parent
SUBMISSION = ROOT / "docs" / "SUBMISSION.md"
DOCS_HTML = ROOT / "docs" / "docs.html"


def sections() -> int:
    """How many top-level sections the documentation page actually renders."""
    try:
        return DOCS_HTML.read_text().count("<h2 id=")
    except OSError:
        return 0


def rewrite(text: str) -> str:
    total, red, e2e, secs = suite.total(), suite.red_team(), suite.end_to_end(), sections()
    subs = [
        (r"\*\*\d+ red-team tests\*\*", f"**{red} red-team tests**"),
        (r"\*\*\d+ tests, network-free", f"**{total} tests, network-free"),
        (r"- \d+, network-free, incl\. \d+ end-to-end \|",
         f"- {total}, network-free, incl. {e2e} end-to-end |"),
        (r"/docs - \d+ sections incl\.", f"/docs - {secs} sections incl."),
    ]
    for pattern, replacement in subs:
        text, n = re.subn(pattern, replacement, text)
        if not n:
            raise SystemExit(f"no sentence in SUBMISSION.md matches {pattern!r}; "
                             f"the prose changed shape and this tool must be updated "
                             f"rather than silently doing nothing")
    return text


def main() -> int:
    current = SUBMISSION.read_text()
    wanted = rewrite(current)
    if "--check" in sys.argv:
        if current != wanted:
            print("docs/SUBMISSION.md quotes stale counts; run "
                  "python3 tools/submission_counts.py", file=sys.stderr)
            return 1
        print(f"SUBMISSION.md counts current: {suite.total()} tests, "
              f"{suite.red_team()} red-team, {suite.end_to_end()} end-to-end, "
              f"{sections()} doc sections")
        return 0
    SUBMISSION.write_text(wanted)
    print(f"rewrote docs/SUBMISSION.md - {suite.total()} tests, "
          f"{suite.red_team()} red-team, {suite.end_to_end()} end-to-end, "
          f"{sections()} doc sections")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
