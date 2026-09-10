"""Does a matched stock perp hedge the overnight risk of an rToken?

Regresses each rToken's overnight return on its perp's over the same window, then
conditions on stress (top-decile moves), calm, and weekend windows, and measures
what the hedge does to the tail.

Measured 2026-09-08: median R^2 0.977, beta within 4% of 1.00, and R^2 RISES to
0.985-1.000 on the largest moves -- the hedge is strongest exactly when it matters.
Median p95 tail reduction 90%.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import statistics as st

from ballast.market import bars
from ballast.overnight import aligned, overnight_returns
from ballast.sessions import window_hours
from ballast.stats import bp, ols, percentile

NAMES = ["TSLA", "NVDA", "AAPL", "MSFT", "AMZN", "META",
         "GOOGL", "SPY", "QQQ", "COIN", "PLTR", "AMD"]
STRESS_DECILE = 0.10


def _subset(idx, xs, ys):
    return ols([xs[i] for i in idx], [ys[i] for i in idx])


def run() -> None:
    print(f"{'name':6s} {'n':>4s} | {'ALL beta':>9s} {'R2':>6s} | "
          f"{'STRESS beta':>12s} {'R2':>6s} | {'CALM beta':>10s} {'R2':>6s} | {'wknd R2':>8s}")
    print("-" * 88)

    r2s, tails = [], []
    for name in NAMES:
        spot = overnight_returns(bars(f"R{name}USDT", "spot"))
        perp = overnight_returns(bars(f"{name}USDT", "mix"))
        dates, ys, xs = aligned(spot, perp)
        if len(dates) < 60:
            continue

        beta, r2, resid = ols(xs, ys)
        order = sorted(range(len(dates)), key=lambda i: abs(ys[i]), reverse=True)
        k = max(12, int(STRESS_DECILE * len(dates)))
        b_s, r2_s, _ = _subset(order[:k], xs, ys)
        b_c, r2_c, _ = _subset(order[len(dates) // 2:], xs, ys)

        wk = [i for i, d in enumerate(dates) if window_hours(d) > 40]
        r2_w = _subset(wk, xs, ys)[1] if len(wk) >= 20 else float("nan")

        r2s.append(r2)
        unh = [abs(v) for v in ys]
        hed = [abs(v) for v in resid]
        tails.append(1 - percentile(hed, 0.95) / percentile(unh, 0.95))

        print(f"{name:6s} {len(dates):4d} | {beta:9.3f} {r2:6.3f} | {b_s:12.3f} {r2_s:6.3f} | "
              f"{b_c:10.3f} {r2_c:6.3f} | {r2_w:8.3f}")

    print("-" * 88)
    print(f"median R2 (variance removed) : {st.median(r2s):.3f}")
    print(f"median p95 tail reduction    : {100 * st.median(tails):.0f}%")


def tail_table() -> None:
    print(f"\n{'name':6s} {'worst_unhedged':>15s} {'worst_hedged':>13s} "
          f"{'p95_unhedged':>13s} {'p95_hedged':>11s}")
    print("-" * 62)
    for name in NAMES:
        spot = overnight_returns(bars(f"R{name}USDT", "spot"))
        perp = overnight_returns(bars(f"{name}USDT", "mix"))
        dates, ys, xs = aligned(spot, perp)
        if len(dates) < 60:
            continue
        _, _, resid = ols(xs, ys)
        unh = [abs(bp(v)) for v in ys]
        hed = [abs(bp(v)) for v in resid]
        print(f"{name:6s} {max(unh):15.0f} {max(hed):13.0f} "
              f"{percentile(unh, 0.95):13.0f} {percentile(hed, 0.95):11.0f}")


if __name__ == "__main__":
    run()
    tail_table()
