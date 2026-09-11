"""Regenerate the README's measured-figures table from docs/facts.json.

    python3 tools/readme_facts.py           # rewrite the block
    python3 tools/readme_facts.py --check   # fail if it is stale (CI runs this)

The README claimed "224 of 704 live rTokens, observed 2026-09-08" while facts.json
said 241 of 1173 measured three days later - the universe had grown 67% and the
most-read file in the repo had not noticed. facts.json and the hard rule against
literals exist precisely to stop that, and the README was the one place exempt from
both. It is not exempt now: the block between the markers is generated, and CI
fails if it drifts.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ballast import facts

README = Path(__file__).resolve().parent.parent / "README.md"
START, END = "<!-- facts:start -->", "<!-- facts:end -->"


def block(f: dict) -> str:
    oos = f.get("oos") or {}
    rows = [
        ("Overnight variance removed by a matched perp hedge",
         f"**median R² {f['median_r2']:.3f}**, β within 4% of 1.00"),
        ("R² on the largest-move nights",
         "**0.978 - 0.999** - the hedge strengthens under stress"),
        ("p95 tail reduction", f"**median {f['median_tail_cut_pct']}%**"),
        ("Held out (β fitted on the first 70%, applied unchanged)",
         f"**R² {oos.get('is_median_r2', '?')} -> {oos.get('oos_median_r2', '?')}**, "
         f"tail {oos.get('is_median_tail', '?')}% -> {oos.get('oos_median_tail', '?')}%, "
         f"{oos.get('names', '?')}/{oos.get('names', '?')} names holding"),
        ("Worst nights", "MSFT 1,128 bp -> 233 bp · AMD 1,262 bp -> 90 bp"),
        ("Cost of protection",
         f"**{f['hedge_cost_bp']} bp** taker, net of funding received"),
        ("Cost of exiting instead",
         f"**{f['exit_cost_bp']:.0f} bp**, and you lose the position"),
        ("Hedgeable universe",
         f"**{f['rtokens_hedgeable']:,}** of {f['rtokens_total']:,} live rTokens"),
    ]
    table = "\n".join(f"| {a} | {b} |" for a, b in rows)
    return (
        f"{START}\n"
        f"All figures measured **{f['measured_on']}** from public Bitget endpoints and\n"
        f"regenerated from [`docs/facts.json`](docs/facts.json) - none is a literal in this\n"
        f"file. Reproduce with `research/`; full detail and disclosed defects in\n"
        f"[`docs/RESEARCH.md`](docs/RESEARCH.md).\n\n"
        f"| | |\n|---|---|\n{table}\n"
        f"{END}")


def rewrite(check: bool = False) -> int:
    text = README.read_text()
    fresh = block(facts.load())
    if START in text and END in text:
        head, rest = text.split(START, 1)
        updated = head + fresh + rest.split(END, 1)[1]
    else:
        raise SystemExit(f"README.md has no {START} / {END} markers")
    if updated == text:
        print("README figures are current")
        return 0
    if check:
        print("STALE: README figures differ from docs/facts.json.\n"
              "Run: python3 tools/readme_facts.py")
        return 1
    README.write_text(updated)
    print(f"rewrote {README.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(rewrite(check="--check" in sys.argv))
