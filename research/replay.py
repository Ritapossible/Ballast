"""Replay the live policy over history — the backtest, and the settlement check.

Every night is decided using ONLY data available before that night: the trailing
return history is truncated at the session, and the event calendar is read for
that date. The same `decide()` the nightly runner calls is the one replayed here,
so the backtest cannot drift from the deployed policy.

Reports portfolio-level metrics hedged versus unhedged on the SAME positions and
the SAME nights. The hedge leg is never shown standalone — on its own it is a
short perp and its Sharpe is meaningless.

    python3 research/replay.py [--start 2025-11-01]
"""
from __future__ import annotations

import argparse
import datetime as dt
import math
import statistics as st
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ballast.earnings import symbols_on
from ballast.executor import PERP_TAKER_FEE
from ballast.market import bars
from ballast.overnight import overnight_returns
from ballast.policy import (Action, EventType, Impact, NightRisk, PolicyConfig,
                            decide)
from ballast.sessions import next_session, window_hours

TICKERS = ["TSLA", "NVDA", "PLTR", "COIN", "AMD", "MSFT",
           "ORCL", "ADBE", "MU", "NKE", "COST", "SPY"]
COST = PERP_TAKER_FEE * 2          # round trip, taker both legs
CFG = PolicyConfig()


def _risk(ticker: str, session: dt.date) -> NightRisk:
    reporting = set(symbols_on(session)) | set(symbols_on(next_session(session)))
    if ticker not in reporting:
        return NightRisk(ticker=ticker)
    return NightRisk(ticker=ticker, event_type=EventType.EARNINGS,
                     expected_impact=Impact.HIGH, confidence=1.0,
                     verbatim_quote=f"{ticker} scheduled to report")


def _metrics(rets: list[float]) -> dict:
    if len(rets) < 5:
        return {}
    mean, sd = st.mean(rets), st.pstdev(rets)
    downside = [r for r in rets if r < 0]
    dsd = st.pstdev(downside) if len(downside) > 1 else 0.0
    ann = math.sqrt(252)
    equity, peak, mdd = 1.0, 1.0, 0.0
    for r in rets:
        equity *= math.exp(r)
        peak = max(peak, equity)
        mdd = max(mdd, 1 - equity / peak)
    return {
        "nights": len(rets),
        "total_%": 100 * (equity - 1),
        "sharpe": ann * mean / sd if sd else float("nan"),
        "sortino": ann * mean / dsd if dsd else float("nan"),
        "max_dd_%": 100 * mdd,
        "vol_ann_%": 100 * sd * ann,
    }


def run(start: dt.date | None) -> None:
    spot, perp, hist = {}, {}, {}
    for t in TICKERS:
        spot[t] = overnight_returns(bars(f"R{t}USDT", "spot"))
        perp[t] = overnight_returns(bars(f"{t}USDT", "mix"))
        hist[t] = sorted(spot[t].items())

    sessions = sorted(set.intersection(*(set(spot[t]) & set(perp[t]) for t in TICKERS)))
    if start:
        sessions = [s for s in sessions if s >= start]

    unhedged_nightly, hedged_nightly = [], []
    decisions = hedges = correct = 0
    worst_un = worst_hd = 0.0

    for session in sessions:
        un_leg, hd_leg = [], []
        for t in TICKERS:
            prior = [v for d, v in hist[t] if d < session]
            d = decide(t, f"R{t}USDT", prior, _risk(t, session), window_hours(session), CFG)
            s_ret, p_ret = spot[t][session], perp[t][session]
            hedged = d.action is Action.HEDGE
            realised = (s_ret - p_ret - COST) if hedged else s_ret

            decisions += 1
            hedges += hedged
            correct += (abs(s_ret) > COST) if hedged else (abs(s_ret) <= COST)
            worst_un = max(worst_un, abs(s_ret))
            worst_hd = max(worst_hd, abs(realised))
            un_leg.append(s_ret)
            hd_leg.append(realised)

        unhedged_nightly.append(st.mean(un_leg))
        hedged_nightly.append(st.mean(hd_leg))

    un, hd = _metrics(unhedged_nightly), _metrics(hedged_nightly)
    print(f"Replay · {len(sessions)} sessions · {len(TICKERS)} equally-weighted positions")
    print(f"{sessions[0]} → {sessions[-1]}\n")
    print(f"{'metric':16s} {'UNHEDGED':>12s} {'BALLAST':>12s} {'change':>12s}")
    print("-" * 56)
    for key, label, better_low in [("total_%", "total return %", False),
                                   ("vol_ann_%", "volatility %", True),
                                   ("sharpe", "Sharpe", False),
                                   ("sortino", "Sortino", False),
                                   ("max_dd_%", "max drawdown %", True)]:
        a, b = un[key], hd[key]
        delta = b - a
        mark = "✓" if (delta < 0) == better_low and abs(delta) > 1e-9 else ""
        print(f"{label:16s} {a:12.2f} {b:12.2f} {delta:+11.2f} {mark}")
    print("-" * 56)
    print(f"nights hedged     {hedges}/{decisions} decisions ({100*hedges/decisions:.0f}%)")
    print(f"decision accuracy {correct}/{decisions} ({100*correct/decisions:.0f}%)")
    print(f"worst single night {1e4*worst_un:.0f}bp unhedged → {1e4*worst_hd:.0f}bp with Ballast")
    print(f"\ncost model: {1e4*COST:.0f}bp round trip, taker both legs, no maker assumed")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--start", type=dt.date.fromisoformat, default=None)
    run(ap.parse_args().start)
