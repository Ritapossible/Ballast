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

# Funding accrues every 8h; a short perp RECEIVES it while the rate is positive
# and PAYS it while the rate is negative. This constant is the mean of 100
# periods on TSLAUSDT, and treating it as the cost of every name was the thing
# wrong with it: measured across the whole book on 2026-09-18 the per-night
# credit runs from -0.19 bp (PLTR) to +3.01 bp (NKE), and the sign is against
# the hedge on 2 of the 12 names held.
#
# So the certain figure is the taker round trip. The funding credit is an
# observed average, not a guarantee, and `funding_observed_bp` reads the real
# rate for a name when the venue can be reached. Nothing here nets a hope into
# a headline: see `hedge_cost_gross_bp`.
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


def funding_observed_bp(symbol: str, periods: int = FUNDING_PERIODS_PER_NIGHT,
                        page_size: int = 100) -> float | None:
    """What a short in THIS name actually collected per night, recently.

    Signed: negative means the short paid. Returns None when the venue cannot be
    reached, because an unavailable rate is not a rate of zero and the caller
    must decide what to do about that rather than be handed a flattering
    default.
    """
    # Imported here, not at module scope: costs.py is the one source of truth
    # for the fee schedule and must stay importable without a network stack.
    from . import market

    try:
        rows = market.funding_history(symbol, page_size=page_size)
    except Exception:          # an unreachable venue is "unknown", never "zero"
        return None
    rates = [float(r["fundingRate"]) for r in rows
             if r.get("fundingRate") is not None]
    if not rates:
        return None
    return sum(rates) / len(rates) * periods * 1e4


def hedge_cost_gross_bp(maker: bool = False) -> float:
    """The part of the cost that is certain: the taker round trip, no credits.

    This is what the hedge costs before any funding is collected. It is the
    number to quote when the direction of funding for a given name is unknown.
    """
    return perp_round_trip_bp(maker)


def hedge_cost_bp(maker: bool = False, funding_bp: float | None = None) -> float:
    """Cost of one night's protection, net of funding.

    Defaults to TAKER on both legs. Maker pricing is upside and is never assumed:
    a resting order in a 4am perp book may simply not fill.

    `funding_bp` is the signed credit for the name being hedged; pass the
    measured one where it is known. The default is the book-wide average and is
    therefore the FAVOURABLE case for names whose funding runs negative.
    """
    credit = funding_received_bp() if funding_bp is None else funding_bp
    return perp_round_trip_bp(maker) - credit


def spot_round_trip_bp() -> float:
    """Cost of exiting the position instead - the alternative Ballast replaces."""
    return SPOT_TAKER_FEE * 2 * 1e4


# The settled record charges this, and has since the first night. It is left
# alone deliberately: changing what a hedge costs part-way through a competition
# record would make the settled table incomparable with itself, which is a worse
# fault than the one being corrected. The correction is that the pages now say
# what is certain (gross) and what is averaged (the credit), instead of quoting
# only the net and calling it the price.
HEDGE_COST_BP = hedge_cost_bp()          # 11.3, net of an averaged credit
HEDGE_COST_GROSS_BP = round(hedge_cost_gross_bp(), 2)   # 12.0, certain
EXIT_COST_BP = spot_round_trip_bp()      # 20.0
