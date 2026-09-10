"""Reproduce every cost figure the site publishes.

The Evidence page claims "every figure on this page is produced by code in the
repository". Two were not: the funding component of the 11.3 bp hedge cost and the
20 bp exit cost both came from throwaway scripts that were never committed. This
closes that gap.

    python3 research/costs_study.py
"""
from __future__ import annotations

import statistics as st
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ballast import costs
from ballast.market import contract, funding_history, spot_symbols

PERPS = ["TSLAUSDT", "NVDAUSDT", "AAPLUSDT", "MSFTUSDT", "AMZNUSDT",
         "METAUSDT", "GOOGLUSDT", "SPYUSDT", "QQQUSDT"]


def perp_fees() -> tuple[float, float]:
    takers, makers = [], []
    for symbol in PERPS:
        spec = contract(symbol)
        takers.append(float(spec["takerFeeRate"]))
        makers.append(float(spec["makerFeeRate"]))
    return st.median(takers), st.median(makers)


def spot_fees() -> tuple[float, float, int]:
    rtokens = [s for s in spot_symbols()
               if s.get("status") == "online" and s["baseCoin"][:1] == "r"
               and s["baseCoin"][1:2].isupper()]
    takers = {float(s["takerFeeRate"]) for s in rtokens}
    makers = {float(s["makerFeeRate"]) for s in rtokens}
    return max(takers), max(makers), len(rtokens)


def funding() -> tuple[float, float, int]:
    rates: list[float] = []
    for symbol in PERPS:
        rates += [float(r["fundingRate"]) for r in funding_history(symbol)]
    return st.mean(rates), st.median(rates), len(rates)


def run() -> None:
    print("Cost figures, measured from public Bitget endpoints\n")

    taker, maker = perp_fees()
    print(f"perp taker fee            {taker:.5f}  ({taker * 1e4:.0f} bp per side)")
    print(f"perp maker fee            {maker:.5f}  ({maker * 1e4:.0f} bp per side)")

    s_taker, s_maker, n_rtokens = spot_fees()
    print(f"rToken spot taker fee     {s_taker:.5f}  ({s_taker * 1e4:.0f} bp per side)")
    print(f"rToken spot maker fee     {s_maker:.5f}  ({s_maker * 1e4:.0f} bp per side)"
          f"{'   <- no maker discount' if s_maker >= s_taker else ''}")
    print(f"rTokens sampled           {n_rtokens}")

    mean_rate, median_rate, n = funding()
    per_night = mean_rate * costs.FUNDING_PERIODS_PER_NIGHT * 1e4
    print(f"\nfunding, mean per 8h      {mean_rate:.7f}  ({mean_rate * 1e4:.3f} bp)")
    print(f"funding, median per 8h    {median_rate:.7f}  (mostly zero; it is sparse)")
    print(f"funding periods sampled   {n}")
    print(f"annualised                {mean_rate * 3 * 365 * 100:.2f}%  "
          f"- positive, so a SHORT perp receives it")

    print(f"\n{'derived':26s} {'measured':>10s} {'published':>11s}")
    print("-" * 50)
    checks = [
        ("hedge round trip, taker", taker * 2 * 1e4, costs.perp_round_trip_bp()),
        ("funding received / night", per_night, costs.funding_received_bp()),
        ("net hedge cost", taker * 2 * 1e4 - per_night, costs.HEDGE_COST_BP),
        ("exit cost (spot round trip)", s_taker * 2 * 1e4, costs.EXIT_COST_BP),
    ]
    drift = False
    for label, measured, published in checks:
        ok = abs(measured - published) < 0.5
        drift = drift or not ok
        print(f"{label:26s} {measured:9.2f}bp {published:10.2f}bp  {'ok' if ok else 'DRIFT'}")

    print("\n" + ("Fees have moved - update ballast/costs.py." if drift
                  else "costs.py matches the live fee schedule."))


if __name__ == "__main__":
    run()
