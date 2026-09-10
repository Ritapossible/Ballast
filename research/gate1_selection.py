"""GATE 1 — can high-risk nights be selected EX-ANTE?

A delta hedge is symmetric: it removes upside with downside. Ballast therefore
creates value only if the nights it hedges carry variance WITHOUT compensation.

Two things must hold for a statistical selector to be usable:
  (a) SEPARATION -- selected nights must actually be higher variance;
  (b) NEUTRALITY -- their mean return must not be reliably positive.

This script tests trailing realised overnight volatility as the selector, using
strictly prior nights only. A `--lookahead` mode reproduces the INVALID
ex-post selection for contrast; it exists to document the bug, not to be used.

Result (2026-09-08, 12 names): separation FAILS. Variance ratio 1.03x ex-ante
versus 13.2x ex-post. Trailing vol does not find risky nights -- the selector
must be the event calendar.
"""
from __future__ import annotations

import argparse
import statistics as st

from ballast.costs import HEDGE_COST_BP
from ballast.market import bars
from ballast.overnight import overnight_returns
from ballast.stats import bp, t_stat

NAMES = ["TSLA", "NVDA", "AAPL", "MSFT", "AMZN", "META",
         "GOOGL", "SPY", "QQQ", "COIN", "PLTR", "AMD"]
WINDOW = 20        # trailing nights used to predict tonight
TOP_QUINTILE = 0.80



def run(lookahead: bool = False) -> None:
    mode = "EX-POST (INVALID — documents the bug)" if lookahead else "EX-ANTE (valid)"
    print(f"GATE 1 — selector: trailing {WINDOW}-night realised vol · {mode}\n")
    print(f"{'name':6s} {'n_sel':>6s} {'mean_bp':>9s} {'t':>6s} {'sd_bp':>7s} | "
          f"{'n_rest':>7s} {'mean_bp':>9s} {'t':>6s} {'sd_bp':>7s}")
    print("-" * 74)

    sel_all: list[float] = []
    rest_all: list[float] = []
    for name in NAMES:
        series = overnight_returns(bars(f"R{name}USDT", "spot"))
        rows = sorted(series.items())
        if len(rows) < 80:
            continue

        scored = []
        for i in range(WINDOW, len(rows)):
            night = rows[i][1]
            score = abs(night) if lookahead else st.pstdev([r[1] for r in rows[i - WINDOW:i]])
            scored.append((score, night))

        cut = sorted(s for s, _ in scored)[int(TOP_QUINTILE * len(scored))]
        sel = [v for s, v in scored if s >= cut]
        rest = [v for s, v in scored if s < cut]
        sel_all += sel
        rest_all += rest

        ms, ts_ = t_stat(sel)
        mr, tr = t_stat(rest)
        print(f"{name:6s} {len(sel):6d} {bp(ms):9.1f} {ts_:6.2f} {bp(st.pstdev(sel)):7.0f} | "
              f"{len(rest):7d} {bp(mr):9.1f} {tr:6.2f} {bp(st.pstdev(rest)):7.0f}")

    print("-" * 74)
    ms, ts_ = t_stat(sel_all)
    mr, _ = t_stat(rest_all)
    ratio = st.pvariance(sel_all) / st.pvariance(rest_all)
    print(f"POOLED selected : n={len(sel_all):4d}  mean={bp(ms):+7.1f} bp  t={ts_:+5.2f}  "
          f"sd={bp(st.pstdev(sel_all)):5.0f} bp")
    print(f"POOLED rest     : n={len(rest_all):4d}  mean={bp(mr):+7.1f} bp")
    print(f"\n(a) SEPARATION  variance ratio selected/rest = {ratio:.2f}x  "
          f"-> {'PASS' if ratio >= 2 else 'FAIL — selector has no power'}")
    print(f"(b) NEUTRALITY  |t| on selected nights = {abs(ts_):.2f}  "
          f"-> {'compensated (Positioning B)' if abs(ts_) >= 2 else 'uncompensated (Positioning A)'}")
    print(f"\nforgone expected return if hedged: {bp(ms):.1f} bp/night vs "
          f"{HEDGE_COST_BP} bp cost")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--lookahead", action="store_true",
                    help="reproduce the invalid ex-post selection, for contrast only")
    run(**vars(ap.parse_args()))
