"""Resolve the hedgeable universe: rTokens that have a matched stock perp.

Identification rule (measured 2026-09-08): an rToken is identified by its
`baseCoin` matching ^r[A-Z] -- e.g. `rPBR`. Do NOT regex the `symbol` field:
RUNEUSDT, ROSEUSDT, RAYUSDT and REDUSDT are crypto assets, not stocks.

Stock perps use the BARE ticker: rTSLA (spot) hedges against TSLAUSDT (perp).

A bare ticker is NOT enough on its own. Bitget lists 300 stock perps and 477
crypto perps in the same USDT-futures namespace, and 34 of them collide: rF is
tokenized Ford, and FUSDT is a crypto perp with base coin F. Pairing on the name
alone matched Ford against it -- and against rSUI/SUIUSDT, rC/CUSDT, rBCH/BCHUSDT
and 30 more -- which would have hedged a stock with an unrelated crypto. The
measured tracking on those pairs is R^2 ~= 0.00, against ~0.99 on a real pair.

So the perp leg is also required to be symbolType == "stock", which only the v3
instruments endpoint reports (v2 returns "perpetual" for every contract). No
position in the book was ever mispaired -- all 12 legs are stock perps -- but
`Book.from_tickers` would have accepted one, so this is a gate, not a display
filter.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from .market import futures_tickers, instruments, spot_symbols

_RTOKEN = re.compile(r"^r[A-Z]")


@dataclass(frozen=True)
class Pair:
    ticker: str        # "TSLA"
    spot: str          # "RTSLAUSDT"
    perp: str          # "TSLAUSDT"


@dataclass(frozen=True)
class Unpaired:
    ticker: str        # "SBUX"
    spot: str          # "RSBUXUSDT"


def split_universe() -> tuple[list[Pair], list[Unpaired]]:
    """Both sides of the listing in ONE pass over the two endpoints.

    The coverage index needs the hedgeable and the unhedgeable halves together and
    needs the bare ticker for each, which the two older accessors cannot give
    without three API calls and a second copy of the rToken rule. They are kept as
    the narrow public names and now read off this.
    """
    # Tradeable AND classified as a stock perp. The first set answers "can an
    # order rest here", the second "is this the same company"; a name needs both.
    tradeable = {t["symbol"] for t in futures_tickers()}
    perps = {
        i["symbol"] for i in instruments("USDT-FUTURES")
        if i.get("symbolType") == "stock" and i.get("status") == "online"
    } & tradeable
    pairs, unpaired = [], []
    for s in spot_symbols():
        if s.get("status") != "online" or not _RTOKEN.match(s["baseCoin"]):
            continue
        ticker = s["baseCoin"][1:]
        perp = f"{ticker}USDT"
        if perp in perps:
            pairs.append(Pair(ticker=ticker, spot=s["symbol"], perp=perp))
        else:
            unpaired.append(Unpaired(ticker=ticker, spot=s["symbol"]))
    return (sorted(pairs, key=lambda p: p.ticker),
            sorted(unpaired, key=lambda u: u.spot))


def hedgeable_pairs() -> list[Pair]:
    """Every rToken with a tradeable perp leg. 219 of 699 as of 2026-09-08."""
    return split_universe()[0]


def unhedgeable_rtokens() -> list[str]:
    """rTokens with no perp leg. Ballast cannot protect these, and says so."""
    return [u.spot for u in split_universe()[1]]


if __name__ == "__main__":
    hedgeable = hedgeable_pairs()
    print(f"hedgeable pairs : {len(hedgeable)}")
    print(f"unhedgeable     : {len(unhedgeable_rtokens())}")
    print("sample          :", ", ".join(p.ticker for p in hedgeable[:20]))
