"""The coverage index: for every listed rToken, can Ballast protect it?

The site could state how many names have a perp leg but never which, so a visitor
holding one of the 1,173 had no way to ask about their own position. This builds
the answer for all of them at once, as a flat JSON file the page reads.

Three things are deliberate.

FIT IS MEASURED, NOT ASSERTED. A name is not "covered" because a perp exists; it
is covered because the perp demonstrably tracked it. Each pair is regressed over a
bounded recent window and the beta and R-squared are published per name, so a
thin or badly-tracking pair is visible as a low R-squared rather than hidden
behind a checkmark.

THE WINDOW IS SHORT ON PURPOSE. `research/hedge_study.py` pages back 467 days per
symbol, which is ~56 requests. Across 480 legs that is 27,000 requests and hours
of wall clock - not something to run on a schedule. One bounded page per leg
yields ~28 paired nights, enough for a fit worth publishing and cheap enough to
refresh. The published `window_nights` says which it is, and the research figures
remain the deep ones.

THE SHARED CANDLE CACHE IS NOT TOUCHED. `market.candles` keys its cache by symbol
alone, so a truncated pull written under that key would be served to the nightly
decision run, silently shortening the sigma history and the settlement series.
Every fetch here passes use_cache=False for that reason. Do not "optimise" it.

Carries no claim about the ledger, so unlike the page builders it needs no signing
key and is safe to run anywhere.
"""
from __future__ import annotations

import datetime as dt
import json
import statistics as st
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from . import config
from .costs import HEDGE_COST_BP
from .market import bars
from .overnight import aligned, overnight_returns
from .stats import ols
from .universe import Pair, split_universe

OUT = config.ROOT / "docs" / "coverage.json"

WINDOW_BARS = 1000    # ~42 calendar days, which is ~28 weekday overnight windows
MIN_NIGHTS = 10       # below this a beta is noise, and is published as no fit
WORKERS = 6           # polite against a public endpoint; 240 names in ~3 minutes


def _fit(pair: Pair) -> dict:
    """One name's hedge fit, or a stated reason there isn't one.

    Every failure is caught and named rather than raised: one delisted leg or one
    timeout must not cost the other 239 names their row.
    """
    row: dict = {"ticker": pair.ticker, "spot": pair.spot, "perp": pair.perp}
    try:
        spot = overnight_returns(
            bars(pair.spot, "spot", max_bars=WINDOW_BARS, use_cache=False))
        perp = overnight_returns(
            bars(pair.perp, "mix", max_bars=WINDOW_BARS, use_cache=False))
    except Exception as exc:  # one bad leg must not cost the other names their row
        return row | {"nights": 0, "fit": None, "why": type(exc).__name__}

    _, ys, xs = aligned(spot, perp)
    row["nights"] = len(ys)
    if len(ys) < MIN_NIGHTS:
        return row | {"fit": None, "why": "too few paired nights"}
    try:
        beta, r2, _ = ols(xs, ys)
    except ValueError as exc:
        return row | {"fit": None, "why": str(exc)}

    return row | {
        "fit": True,
        "beta": round(beta, 3),
        "r2": round(r2, 3),
        "typical_bp": round(st.median(abs(y) * 1e4 for y in ys), 1),
    }


def build(out: Path | None = None) -> Path:
    pairs, unpaired = split_universe()
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        covered = list(pool.map(_fit, pairs))

    payload = {
        "measured_on": dt.date.today().isoformat(),
        "window_nights": WINDOW_BARS // 24,
        "hedge_cost_bp": HEDGE_COST_BP,
        "counts": {
            "rtokens": len(pairs) + len(unpaired),
            "covered": len(covered),
            "uncovered": len(unpaired),
            "fitted": sum(1 for c in covered if c["fit"]),
        },
        "covered": sorted(covered, key=lambda c: c["ticker"]),
        "uncovered": [u.ticker for u in unpaired],
    }
    path = out or OUT
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=1, sort_keys=True) + "\n")
    return path


if __name__ == "__main__":
    p = build()
    d = json.loads(p.read_text())
    c = d["counts"]
    print(f"wrote {p.name} ({p.stat().st_size:,} bytes)")
    print(f"  {c['rtokens']} rTokens · {c['covered']} covered "
          f"({c['fitted']} with a fit) · {c['uncovered']} with no perp leg")
