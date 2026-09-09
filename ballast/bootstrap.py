"""Create the paper position book.

Ballast protects positions it did not open, so the book has to come from
somewhere. This builds an equal-notional paper portfolio for the competition run.

    python -m ballast.bootstrap --usdt-each 1000
"""
from __future__ import annotations

import argparse

from . import config
from .book import Book
from .market import closes
from .universe import hedgeable_pairs

# Liquid, high-overnight-variance names, plus two ETFs as low-vol controls.
# ORCL / ADBE / MU / NKE / COST report inside the 2026-09 competition window,
# which is what makes the earnings use case demonstrable live.
DEFAULT_TICKERS = ["TSLA", "NVDA", "PLTR", "COIN", "AMD", "MSFT",
                   "ORCL", "ADBE", "MU", "NKE", "COST", "SPY"]


def run(tickers: list[str], usdt_each: float) -> dict:
    pairs = {p.ticker: p for p in hedgeable_pairs()}
    unknown = [t for t in tickers if t not in pairs]
    if unknown:
        raise SystemExit(f"not hedgeable (no perp leg): {', '.join(unknown)}")

    marks = {}
    for t in tickers:
        bars = closes(pairs[t].spot, "spot")
        marks[pairs[t].spot] = bars[max(bars)]

    book = Book.from_tickers(tickers, usdt_each, marks)
    config.STATE.mkdir(parents=True, exist_ok=True)
    book.save(config.BOOK_PATH)
    return {"positions": len(book), "usdt_each": usdt_each,
            "total_usdt": usdt_each * len(book), "path": str(config.BOOK_PATH)}


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--tickers", nargs="*", default=DEFAULT_TICKERS)
    ap.add_argument("--usdt-each", type=float, default=1000.0)
    r = run(ap.parse_args().tickers, ap.parse_args().usdt_each)
    print(f"book written: {r['positions']} positions, "
          f"{r['usdt_each']:.0f} USDT each ({r['total_usdt']:.0f} total)")
    print(f"  -> {r['path']}")
