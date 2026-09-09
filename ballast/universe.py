"""Resolve the hedgeable universe: rTokens that have a matched stock perp.

Identification rule (measured 2026-09-08): an rToken is identified by its
`baseCoin` matching ^r[A-Z] -- e.g. `rPBR`. Do NOT regex the `symbol` field:
RUNEUSDT, ROSEUSDT, RAYUSDT and REDUSDT are crypto assets, not stocks.

Stock perps use the BARE ticker: rTSLA (spot) hedges against TSLAUSDT (perp).
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from .market import futures_tickers, spot_symbols

_RTOKEN = re.compile(r"^r[A-Z]")


@dataclass(frozen=True)
class Pair:
    ticker: str        # "TSLA"
    spot: str          # "RTSLAUSDT"
    perp: str          # "TSLAUSDT"


def hedgeable_pairs() -> list[Pair]:
    """Every rToken with a tradeable perp leg. 219 of 699 as of 2026-09-08."""
    perps = {t["symbol"] for t in futures_tickers()}
    pairs = []
    for s in spot_symbols():
        if s.get("status") != "online" or not _RTOKEN.match(s["baseCoin"]):
            continue
        ticker = s["baseCoin"][1:]
        perp = f"{ticker}USDT"
        if perp in perps:
            pairs.append(Pair(ticker=ticker, spot=s["symbol"], perp=perp))
    return sorted(pairs, key=lambda p: p.ticker)


def unhedgeable_rtokens() -> list[str]:
    """rTokens with no perp leg. Ballast cannot protect these, and says so."""
    perps = {t["symbol"] for t in futures_tickers()}
    return sorted(
        s["symbol"] for s in spot_symbols()
        if s.get("status") == "online"
        and _RTOKEN.match(s["baseCoin"])
        and f"{s['baseCoin'][1:]}USDT" not in perps
    )


if __name__ == "__main__":
    hedgeable = hedgeable_pairs()
    print(f"hedgeable pairs : {len(hedgeable)}")
    print(f"unhedgeable     : {len(unhedgeable_rtokens())}")
    print("sample          :", ", ".join(p.ticker for p in hedgeable[:20]))
