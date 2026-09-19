"""Re-measure the facts the public pages quote, and write docs/facts.json.

    python3 research/facts_study.py
"""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ballast import config, costs, facts
from ballast.book import Book
from ballast.universe import hedgeable_pairs, unhedgeable_rtokens


def funding_spread() -> dict:
    """What a short actually collects, per name, across the book.

    costs.py used to subtract one averaged credit from every hedge and publish
    the result as the price. Measured across the book the per-night credit runs
    from negative to several basis points, so the averaged figure is the
    favourable case for some names and the unfavourable case for others. That
    range belongs on the site rather than inside a constant.
    """
    rows = []
    for pos in Book.load(config.BOOK_PATH):
        got = costs.funding_observed_bp(pos.perp_symbol)
        if got is not None:
            rows.append((pos.ticker, round(got, 2)))
    if not rows:
        return {}
    rows.sort(key=lambda r: r[1])
    values = [v for _, v in rows]
    return {
        "measured_on": dt.date.today().isoformat(),
        "names": len(rows),
        "mean_bp": round(sum(values) / len(values), 2),
        "min_bp": rows[0][1], "min_name": rows[0][0],
        "max_bp": rows[-1][1], "max_name": rows[-1][0],
        "names_paying": sum(1 for v in values if v < 0),
    }


def run() -> None:
    hedgeable = hedgeable_pairs()
    unhedgeable = unhedgeable_rtokens()
    current = facts.load()

    values = dict(current)
    values.update({
        "measured_on": dt.date.today().isoformat(),
        "rtokens_hedgeable": len(hedgeable),
        "rtokens_total": len(hedgeable) + len(unhedgeable),
        "hedge_cost_bp": round(costs.HEDGE_COST_BP, 1),
        "hedge_cost_gross_bp": round(costs.HEDGE_COST_GROSS_BP, 1),
        "exit_cost_bp": round(costs.EXIT_COST_BP, 1),
    })

    for key in ("rtokens_hedgeable", "rtokens_total"):
        if current.get(key) != values[key]:
            print(f"  drift: {key} {current.get(key)} -> {values[key]}")

    spread = funding_spread()
    if spread:
        values["funding"] = spread
        print(f"  funding: mean {spread['mean_bp']:+.2f} bp/night across "
              f"{spread['names']} names, {spread['min_name']} {spread['min_bp']:+.2f} "
              f"to {spread['max_name']} {spread['max_bp']:+.2f}, "
              f"{spread['names_paying']} paying")
    path = facts.save(values)
    print(f"\nwrote {path}")
    for k, v in sorted(values.items()):
        print(f"  {k:22s} {v}")


if __name__ == "__main__":
    run()
