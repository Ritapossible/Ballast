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
from ballast.costs import HEDGE_COST_BP
from ballast.market import bars
from ballast.overnight import overnight_returns
from ballast.policy import (Action, EventType, Impact, NightRisk, PolicyConfig,
                            decide)
from ballast.sessions import next_session, window_hours

TICKERS = ["TSLA", "NVDA", "PLTR", "COIN", "AMD", "MSFT",
           "ORCL", "ADBE", "MU", "NKE", "COST", "SPY"]
COST = HEDGE_COST_BP / 1e4         # taker round trip, net of funding
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
    decisions = hedges = 0
    hedge_shrank = 0                 # hedges that actually reduced |move|
    per_night: list[tuple[float, float, bool]] = []   # (|unhedged|, |realised|, hedged)

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
            if hedged and abs(realised) < abs(s_ret):
                hedge_shrank += 1
            per_night.append((abs(s_ret), abs(realised), hedged))
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

    # Position-level tail. This is the level the product operates at: a
    # concentrated holder feels one position's night, not a 12-name average.
    ranked = sorted(per_night, key=lambda r: -r[0])
    worst_un = ranked[0][0]
    worst_hd = max(r[1] for r in per_night)
    spent_bp = hedges * COST * 1e4

    print(f"\nPosition-level tail ({decisions} position-nights)")
    print(f"{'cohort':22s} {'n':>5s} {'hedged':>8s} {'mean |move|':>12s} {'mean realised':>14s}")
    print("-" * 66)
    for label, cohort in [("worst 1%", ranked[:max(1, decisions // 100)]),
                          ("worst 5%", ranked[:max(1, decisions // 20)]),
                          ("worst 10%", ranked[:max(1, decisions // 10)]),
                          ("all", per_night)]:
        n = len(cohort)
        h = sum(1 for r in cohort if r[2])
        print(f"{label:22s} {n:5d} {h:7d}  {1e4*sum(r[0] for r in cohort)/n:11.0f}bp "
              f"{1e4*sum(r[1] for r in cohort)/n:13.0f}bp")

    print("-" * 66)
    print(f"hedge rate          {hedges}/{decisions} position-nights ({100*hedges/decisions:.1f}%)")
    if hedges:
        print(f"hedges that shrank the move  {hedge_shrank}/{hedges} "
              f"({100*hedge_shrank/hedges:.0f}%)")
    print(f"worst position-night {1e4*worst_un:.0f}bp unhedged · "
          f"worst realised {1e4*worst_hd:.0f}bp")
    print(f"total spent         {spent_bp:.0f}bp across {decisions} position-nights "
          f"({spent_bp/decisions:.1f}bp average drag)")
    print(f"\ncost model: {1e4*COST:.0f}bp round trip, taker both legs, no maker assumed")
    print("note: 'win rate' is reported as the share of hedges that reduced |move|.")
    print("      A hedge is symmetric, so a P&L-direction win rate would be meaningless.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--start", type=dt.date.fromisoformat, default=None)
    run(ap.parse_args().start)
