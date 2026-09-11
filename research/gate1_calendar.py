"""GATE 1, second half — are EARNINGS nights compensated or uncompensated?

Gate 1's first half tested a statistical selector (trailing realised volatility) and
it failed on separation: 1.41x versus 13.2x for the same nights chosen with
hindsight. The conclusion was that the selector must be the event calendar.

This tests the calendar as the selector, on both conditions:

  (a) SEPARATION -- do earnings nights actually carry more variance?
  (b) NEUTRALITY -- is their mean return distinguishable from zero?

(b) decides how the product may be described. If earnings nights are roughly
zero-mean, hedging them removes UNCOMPENSATED variance and Ballast may claim a
risk-adjusted improvement. If they carry positive expected return, hedging forgoes
it and Ballast is priced protection only.

Reported per name AND pooled. The pooled t-statistic is inflated because names move
together on the same nights, so the per-name column is the honest one.

    python3 research/gate1_calendar.py
"""
from __future__ import annotations

import datetime as dt
import math
import statistics as st
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ballast.costs import HEDGE_COST_BP
from ballast.earnings import build_calendar
from ballast.market import bars
from ballast.overnight import overnight_returns
from ballast.sessions import next_session
from ballast.stats import bp, t_stat

TICKERS = ["TSLA", "NVDA", "AAPL", "MSFT", "AMZN", "META", "GOOGL",
           "COIN", "PLTR", "AMD", "ORCL", "ADBE", "MU", "NKE", "COST"]

# Bounded to the window where BOTH the earnings cache and the perp series exist.
# Widening this triggers a fresh calendar crawl and a full re-page of every ticker.
START = dt.date(2025, 10, 1)


def run() -> None:
    series = {t: {d: v for d, v in overnight_returns(bars(f"R{t}USDT", "spot")).items()
                  if d >= START}
              for t in TICKERS}
    span = [d for s in series.values() for d in s]
    cal = build_calendar(START, max(span), set(TICKERS))

    print("GATE 1b — the EVENT CALENDAR as the selector\n")
    print(f"{'name':6s} {'n_earn':>7s} {'mean_bp':>9s} {'t':>6s} {'sd_bp':>7s} | "
          f"{'n_other':>8s} {'mean_bp':>9s} {'sd_bp':>7s} | {'var ratio':>9s}")
    print("-" * 78)

    earn_all: list[float] = []
    other_all: list[float] = []
    ratios: list[float] = []

    for t in TICKERS:
        nights = series[t]
        # An earnings release after the close of session D, or before the open of
        # the next session, both land inside D's close->open window.
        dates = cal.get(t, set())
        flagged = {d for d in nights
                   if d in dates or next_session(d) in dates}
        earn = [v for d, v in nights.items() if d in flagged]
        other = [v for d, v in nights.items() if d not in flagged]
        if len(earn) < 3 or len(other) < 30:
            continue

        earn_all += earn
        other_all += other
        ratio = st.pvariance(earn) / st.pvariance(other) if st.pvariance(other) else float("nan")
        ratios.append(ratio)
        me, te = t_stat(earn) if len(earn) >= 8 else (st.mean(earn), float("nan"))
        mo, _ = t_stat(other)
        print(f"{t:6s} {len(earn):7d} {bp(me):9.1f} {te:6.2f} {bp(st.pstdev(earn)):7.0f} | "
              f"{len(other):8d} {bp(mo):9.1f} {bp(st.pstdev(other)):7.0f} | {ratio:9.1f}x")

    print("-" * 78)
    me, te = t_stat(earn_all)
    mo, to = t_stat(other_all)
    ratio = st.pvariance(earn_all) / st.pvariance(other_all)
    print(f"POOLED earnings nights : n={len(earn_all):4d}  mean={bp(me):+7.1f} bp  "
          f"t={te:+5.2f}  sd={bp(st.pstdev(earn_all)):5.0f} bp")
    print(f"POOLED other nights    : n={len(other_all):4d}  mean={bp(mo):+7.1f} bp  "
          f"t={to:+5.2f}  sd={bp(st.pstdev(other_all)):5.0f} bp")

    se = st.stdev(earn_all) / math.sqrt(len(earn_all))
    print(f"\n(a) SEPARATION  variance ratio earnings/other = {ratio:.1f}x  -> "
          f"{'PASS' if ratio >= 2 else 'FAIL'}  (median per name {st.median(ratios):.1f}x)")
    print(f"(b) NEUTRALITY  pooled |t| = {abs(te):.2f}, 95% CI "
          f"[{bp(me - 1.96 * se):+.0f}, {bp(me + 1.96 * se):+.0f}] bp  -> "
          f"{'compensated' if abs(te) >= 2 else 'UNCOMPENSATED'}")
    signif = sum(1 for t in TICKERS
                 if (lambda e: len(e) >= 8 and abs(t_stat(e)[1]) >= 2)(
                     [v for d, v in series[t].items()
                      if d in cal.get(t, set()) or next_session(d) in cal.get(t, set())]))
    print(f"                per-name significant at |t|>=2: {signif}/{len(TICKERS)}")
    print(f"\nhedge cost {HEDGE_COST_BP}bp vs earnings-night 1-sigma "
          f"{bp(st.pstdev(earn_all)):.0f}bp")


if __name__ == "__main__":
    run()
