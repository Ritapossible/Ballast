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

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ballast import facts, suite

ROOT = Path(__file__).resolve().parent.parent
SUBMISSION = ROOT / "docs" / "SUBMISSION.md"
HACKATHON = ROOT / "docs" / "HACKATHON.md"
DOCS_HTML = ROOT / "docs" / "docs.html"
LEDGER = ROOT / "state" / "ledger.jsonl"


def hub_hedges() -> int:
    """Hedges actually routed to the Agent Hub, counted from the chain.

    HACKATHON.md stated this as prose and it has now drifted twice - five, then
    seven, while the ledger held seven and then nine. It is the row a judge reads
    to learn what the Hub integration really does, and the direction of the drift
    always undercounts the evidence. A hedge carries `venue_fallback` only once an
    order has been sent and the exchange has answered, so that field is the
    definition rather than a proxy for it.
    """
    if not LEDGER.exists():
        return 0
    n = 0
    for line in LEDGER.read_text().splitlines():
        if not line.strip():
            continue
        entry = json.loads(line)
        if entry.get("kind") != "decision":
            continue
        body = entry.get("body") or {}
        if body.get("action") == "HEDGE" and (body.get("fill") or {}).get("venue_fallback"):
            n += 1
    return n


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


def rewrite_hackathon(text: str) -> str:
    """The one generated count in the handbook map."""
    n = hub_hedges()
    word = {7: "seven", 8: "eight", 9: "nine", 10: "ten", 11: "eleven",
            12: "twelve", 13: "thirteen"}.get(n, str(n))
    pattern = r"each of the \w+ hedges since 2026-09-14 was routed"
    text, hits = re.subn(pattern, f"each of the {word} hedges since 2026-09-14 "
                                  f"was routed", text)
    if not hits:
        raise SystemExit(f"no sentence in HACKATHON.md matches {pattern!r}; the "
                         f"prose changed shape and this tool must be updated "
                         f"rather than silently doing nothing")
    return text


def main() -> int:
    current = SUBMISSION.read_text()
    wanted = rewrite(current)
    hack_now = HACKATHON.read_text()
    hack_want = rewrite_hackathon(hack_now)
    if "--check" in sys.argv:
        if hack_now != hack_want:
            print("docs/HACKATHON.md quotes a stale Agent Hub hedge count; run "
                  "python3 tools/submission_counts.py", file=sys.stderr)
            return 1
        if current != wanted:
            print("docs/SUBMISSION.md quotes stale counts; run "
                  "python3 tools/submission_counts.py", file=sys.stderr)
            return 1
        print(f"SUBMISSION.md counts current: {suite.total()} tests, "
              f"{suite.red_team()} red-team, {suite.end_to_end()} end-to-end, "
              f"{sections()} doc sections, "
              f"{facts.load()['rtokens_hedgeable']:,} hedgeable rTokens, "
              f"{hub_hedges()} Agent Hub hedges")
        return 0
    SUBMISSION.write_text(wanted)
    if hack_now != hack_want:
        HACKATHON.write_text(hack_want)
        print(f"rewrote docs/HACKATHON.md - {hub_hedges()} Agent Hub hedges")
    print(f"rewrote docs/SUBMISSION.md - {suite.total()} tests, "
          f"{suite.red_team()} red-team, {suite.end_to_end()} end-to-end, "
          f"{sections()} doc sections, "
          f"{facts.load()['rtokens_hedgeable']:,} hedgeable rTokens")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
