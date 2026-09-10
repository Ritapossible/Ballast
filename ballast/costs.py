"""One source of truth for what a hedge costs.

Three different numbers for the same thing were in use: the policy quoted 11.3 bp,
settlement charged 12.0 bp, and the executor applied fees separately. The site
advertised a price it did not settle at. Everything now derives from the observed
fee schedule here.

All figures observed from Bitget on 2026-09-08 and reproduced by
`research/costs_study.py`.
"""
from __future__ import annotations

# --- observed fee schedule ---------------------------------------------------
PERP_TAKER_FEE = 0.0006          # 0.06% per side, USDT-futures
PERP_MAKER_FEE = 0.0002          # 0.02% per side
SPOT_TAKER_FEE = 0.0010          # 0.10% per side, rToken spot - no maker discount
SPOT_MAKER_FEE = 0.0010

# Funding accrues every 8h; a short perp RECEIVES it while the rate is positive.
# Measured mean +0.00354% per period over 100 periods on TSLAUSDT.
FUNDING_PER_PERIOD = 0.0000354
FUNDING_PERIODS_PER_NIGHT = 2    # a 17.5h window crosses two 8h boundaries

# Modelled, not observed: an off-hours book is thin and we never assume a fill.
SLIPPAGE_BP = 2.0


def perp_round_trip_bp(maker: bool = False) -> float:
    """Cost of opening and closing the hedge leg, in basis points."""
    fee = PERP_MAKER_FEE if maker else PERP_TAKER_FEE
    return fee * 2 * 1e4


def funding_received_bp(periods: int = FUNDING_PERIODS_PER_NIGHT) -> float:
    """Funding a short perp collects over one overnight window."""
    return FUNDING_PER_PERIOD * periods * 1e4


def hedge_cost_bp(maker: bool = False) -> float:
    """Net cost of one night's protection.

    Defaults to TAKER on both legs. Maker pricing is upside and is never assumed:
    a resting order in a 4am perp book may simply not fill.
    """
    return perp_round_trip_bp(maker) - funding_received_bp()


def spot_round_trip_bp() -> float:
    """Cost of exiting the position instead - the alternative Ballast replaces."""
    return SPOT_TAKER_FEE * 2 * 1e4


HEDGE_COST_BP = hedge_cost_bp()          # 11.3
EXIT_COST_BP = spot_round_trip_bp()      # 20.0
