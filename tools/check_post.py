#!/usr/bin/env python3
"""Compare the X drafts against the record, right before posting.

The drafts quote figures that move every night - the chain, the paper metrics,
the second opinion, the universe - and a post is the one artifact that cannot be
corrected after it is sent.

These checks used to live in the unit suite, and that was the wrong shape: every
nightly ledger commit moved the chain under the drafts and turned CI red, on a
schedule, for drafts nobody had touched. A suite that goes red on its own clock
teaches everyone to ignore it. So, as in the sibling project, it is a command you
run in the minute before posting:

    python3 tools/check_post.py

It reads the ledger, docs/facts.json and state/ only - no network. Every
occurrence is checked, against a whitespace-flattened copy so a figure wrapped
across two lines is still seen. Exit status is 1 if anything disagrees.
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from ballast import facts, suite
from ballast.metrics import paper_metrics
from ballast.report import Site

DOCS = ROOT / "docs"
MINUS = "\u2212"


def _flat(text: str) -> str:
    return re.sub(r"\s+", " ", text)


def _decisions() -> list[dict]:
    path = ROOT / "state" / "ledger.jsonl"
    return [json.loads(line)["body"] for line in path.read_text().splitlines()
            if line.strip() and json.loads(line).get("kind") == "decision"]


def expectations() -> list[tuple[str, str, list[str], str]]:
    """(file, what it is, every way the draft writes it, the value it must carry)."""
    f = facts.load()
    total, hedgeable = f["rtokens_total"], f["rtokens_hedgeable"]

    dec = _decisions()
    by = Counter(d["inputs"].get("decided_by") for d in dec)
    why = Counter((d.get("reader") or {}).get("rejected_because")
                  for d in dec if d["inputs"].get("decided_by") == "rule")

    site = Site()
    m = paper_metrics(site.rows, graded=site.clean)
    graded, cut = m["hedges"], m["hedges_that_cut"]
    dd_h, dd_u = round(m["hedged_max_dd_bp"]), round(m["unhedged_max_dd_bp"])

    cc = json.loads((ROOT / "state" / "calendar_crosscheck.json").read_text())["counts"]

    art, post = "X_ARTICLE.md", "X_POST.md"
    out = [
        (art, "tokenized stocks listed", [r"Bitget lists ([\d,]+) tokenized"], f"{total:,}"),
        (art, "universe behind the hedge", [r"Of those ([\d,]+) rTokens"], f"{total:,}"),
        (art, "names with a matched perp", [r"\*\*(\d+) have a matched stock perpetual"],
         str(hedgeable)),
        (post, "hedgeable of the universe", [r"(\d+) of [\d,]+ rTokens"], str(hedgeable)),
        (post, "universe", [r"\d+ of ([\d,]+) rTokens"], f"{total:,}"),

        (art, "decisions on the chain", [r"Over (\d+) decisions on the live chain"],
         str(len(dec))),
        (art, "decided by the model", [r"\*\*(\d+) decided by the model"], str(by["model"])),
        (art, "decided by the rule", [r"decided by the model, (\d+) by the rule"],
         str(by["rule"])),
        (art, "refused for an unsourced quote", [r"\*\*(\d+) answers for quoting a headline"],
         str(why["quote_not_in_sources"])),
        (art, "refused for schema", [r"and (\d+) for schema violations"],
         str(why["schema_violation"])),
        (art, "rule took over, model unreachable", [r"took over on (\d+) nights"],
         str(why["model_unavailable"])),
        (art, "model abstained", [r"remaining (\d+) the model answered cleanly"],
         str(why[None])),

        (art, "settled nights", [r"(\d+) nights, \d+ position-nights, decided"],
         str(m["nights"])),
        (art, "position-nights", [r"\d+ nights, (\d+) position-nights, decided"],
         str(m["positions"])),
        (art, "graded hedges that cut", [r"\*\*(\d+) of \d+ graded hedges cut"], str(cut)),
        (art, "graded hedges", [r"\*\*\d+ of (\d+) graded hedges cut"], str(graded)),
        (art, "drawdown with Ballast",
         [rf"Max drawdown {MINUS}(\d+) bp, against"], str(abs(dd_h))),
        (art, "drawdown untouched",
         [rf"against {MINUS}(\d+) bp untouched"], str(abs(dd_u))),
        (art, "protection", [r"That's the claim: (\d+) bp of"], str(abs(dd_u) - abs(dd_h))),
        (art, "return with Ballast", [r"Total return \+?(-?\d+) bp, against"],
         f"{round(m['hedged_total_bp'])}"),
        (art, "return untouched", [r"against \+?(-?\d+) bp untouched\.\*\* The book"],
         f"{round(m['unhedged_total_bp'])}"),
        (art, "Sharpe with Ballast", [r"Sharpe is ([+-]\d+\.\d+) vs"],
         f"{m['hedged_sharpe']:+.2f}"),
        (art, "Sharpe untouched", [r"Sharpe is [+-]\d+\.\d+ vs ([+-]\d+\.\d+)"],
         f"{m['unhedged_sharpe']:+.2f}"),
        (art, "hedges sent", [r"(\d+) hedges over \d+ nights cannot"], str(m["orders"])),
        (art, "nights behind the no-claim", [r"\d+ hedges over (\d+) nights cannot"],
         str(m["nights"])),

        (art, "suite size", [r"(\d+) tests, requires the enforcer"], str(suite.total())),
    ]
    if cc.get("checked"):
        out += [
            (art, "second opinion: decisions", [r"Across (\d+) decisions it agrees"],
             str(cc["decisions"])),
            (art, "second opinion: agrees", [r"it agrees on (\d+) and disagrees"],
             str(cc["agreed"])),
            (art, "second opinion: disagrees", [r"and disagrees on (\d+)\."],
             str(cc["disagreed"])),
        ]
    else:
        # Down right now: an agreement count in the article is the last good
        # number, which is exactly what fail-closed exists to prevent.
        out.append((art, "second opinion is DOWN - no agreement count may be quoted",
                    [r"it agrees on (\d+)"], "<none>"))
    return out


def matches(text: str, patterns: list[str]) -> list[str]:
    flat = _flat(text)
    found = [m for p in patterns for m in re.findall(p, text)]
    found += [m for p in patterns for m in re.findall(p, flat) if m not in found]
    return found


def main() -> int:
    texts = {name: (DOCS / name).read_text() for name in ("X_ARTICLE.md", "X_POST.md")}
    bad = []
    print("Checking the X drafts against the ledger, facts.json and state/\n")
    for file, what, patterns, expected in expectations():
        found = matches(texts[file], patterns)
        if expected == "<none>":
            ok = not found
            print(f"  [{'ok ' if ok else 'STALE'}] {file}: {what}")
            if not ok:
                bad.append((file, what, "remove the agreement count", f"it says {found}"))
            continue
        if not found:
            print(f"  [GONE ] {file}: {what} - expected {expected}")
            bad.append((file, what, expected, "the draft no longer states it"))
            continue
        wrong = sorted({x for x in found if x != expected})
        print(f"  [{'ok ' if not wrong else 'STALE'}] {file}: {what}: {expected}")
        if wrong:
            bad.append((file, what, expected, f"the draft says {', '.join(wrong)}"))
    if bad:
        print(f"\n{len(bad)} figure(s) disagree with the record:")
        for file, what, expected, why in bad:
            print(f"  - {file}: {what} should be {expected}; {why}")
        print("\nDo not post until the drafts say what the record says.")
        return 1
    print("\nEvery figure in both drafts matches the record.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
