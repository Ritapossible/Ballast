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

The rToken universe counts are here for a different reason. They are measured, not
counted from this repo, and the nightly job rescans them - the universe went from
1,653/218 to 2,125/226 in one scan. Tests already refused the stale figures, so CI
went red on a correct measurement and somebody had to hand-edit two sentences to
clear it. Now the same command that clears the count drift clears this.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ballast import facts, suite

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
    measured = facts.load()
    total_rt, hedgeable = measured["rtokens_total"], measured["rtokens_hedgeable"]
    subs = [
        (r"\*\*\d+ red-team tests\*\*", f"**{red} red-team tests**"),
        (r"\*\*\d+ tests, network-free", f"**{total} tests, network-free"),
        (r"- \d+, network-free, incl\. \d+ end-to-end \|",
         f"- {total}, network-free, incl. {e2e} end-to-end |"),
        (r"/docs - \d+ sections incl\.", f"/docs - {secs} sections incl."),
        (r"Of [\d,]+ live rTokens, \*\*[\d,]+ have a matched stock perpetual\*\*",
         f"Of {total_rt:,} live rTokens, **{hedgeable:,} have a matched stock "
         f"perpetual**"),
        (r"\*\*[\d,]+ of [\d,]+ rTokens have no perp leg\.\*\*",
         f"**{total_rt - hedgeable:,} of {total_rt:,} rTokens have no perp leg.**"),
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
              f"{sections()} doc sections, "
              f"{facts.load()['rtokens_hedgeable']:,} hedgeable rTokens")
        return 0
    SUBMISSION.write_text(wanted)
    print(f"rewrote docs/SUBMISSION.md - {suite.total()} tests, "
          f"{suite.red_team()} red-team, {suite.end_to_end()} end-to-end, "
          f"{sections()} doc sections, "
          f"{facts.load()['rtokens_hedgeable']:,} hedgeable rTokens")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
