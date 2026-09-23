"""Paper-trading performance, on the log run during the competition.

The track is scored 50% quantitatively and names the metrics: paper trading
Sharpe, max drawdown, win rate. The historical replay computed all three; the
LIVE log computed none of them, so the half of the score that is arithmetic had
nothing to read.

Ballast makes no Sharpe claim - it is priced protection, not alpha - and that
stays true. But declining to claim a number is not a reason to withhold it. The
comparison the product is actually about is the same one a drawdown metric asks:
what the book did, against what it would have done untouched.
"""
from __future__ import annotations

import math
import statistics as st

TRADING_NIGHTS_PER_YEAR = 252


def book_series(rows: list[dict]) -> list[tuple[str, float, float]]:
    """(session, hedged_bp, unhedged_bp) per night, equal-weight across positions.

    Hedged is what Ballast produced. Unhedged is the same book with every hedge
    removed - not a model of it, the observed return of the position itself.
    """
    by_session: dict[str, list[dict]] = {}
    for r in rows:
        if r.get("session"):
            by_session.setdefault(r["session"], []).append(r)
    out = []
    for session in sorted(by_session):
        night = by_session[session]
        out.append((session,
                    st.mean(r.get("realised_bp", 0.0) for r in night),
                    st.mean(r.get("unhedged_bp", 0.0) for r in night)))
    return out


def _max_drawdown(returns: list[float]) -> float:
    """Worst peak-to-trough of the cumulative curve, in bp. Zero if never under water."""
    peak = cum = 0.0
    worst = 0.0
    for r in returns:
        cum += r
        peak = max(peak, cum)
        worst = min(worst, cum - peak)
    return worst


def _sharpe(returns: list[float]) -> float:
    """Annualised, zero risk-free. Meaningless below a handful of nights, which is
    why every caller here reports the night count beside it."""
    if len(returns) < 2:
        return float("nan")
    sd = st.stdev(returns)
    if not sd:
        return float("nan")
    return (st.mean(returns) / sd) * math.sqrt(TRADING_NIGHTS_PER_YEAR)


def paper_metrics(rows: list[dict], graded: list[dict] | None = None) -> dict:
    """Every metric the track names, for the hedged book and its counterfactual.

    TWO POPULATIONS, AND THE DIFFERENCE IS NOT COSMETIC.

    `rows` is everything that happened: the book's return, drawdown and Sharpe
    are the record of what this system actually did, defective nights included.
    Removing a bad night from a P&L curve because it was our fault is how a
    track record gets laundered, so nothing is removed here.

    `graded` is the subset a hedge may be *scored* on. Two hedges (2026-09-09
    ORCL and ADBE) covered a night early - defect 3f, disclosed on the page -
    and a hedge aimed at the wrong window cannot evidence how well hedging
    works, whichever way its arithmetic happened to land. They stay in the
    return; they do not count as wins.

    This split is here because the page previously computed the two from
    different sets by accident: the header tile read the graded set and said
    7/7, while this function read every row and said "100%, 9 of 9". Same page,
    same quantity, two answers, and the flattering one was in the bigger type.
    """
    series = book_series(rows)
    hedged = [h for _, h, _ in series]
    unhedged = [u for _, _, u in series]
    scored = rows if graded is None else graded
    hedges = [r for r in scored if r.get("action") == "HEDGE"]
    all_hedges = [r for r in rows if r.get("action") == "HEDGE"]
    cut = sum(1 for r in hedges
              if abs(r.get("realised_bp", 0)) < abs(r.get("unhedged_bp", 0)))

    return {
        "nights": len(series),
        "positions": len(rows),
        "sessions": [s for s, _, _ in series],
        "hedged_total_bp": round(sum(hedged), 1),
        "unhedged_total_bp": round(sum(unhedged), 1),
        "hedged_max_dd_bp": round(_max_drawdown(hedged), 1),
        "unhedged_max_dd_bp": round(_max_drawdown(unhedged), 1),
        "hedged_sharpe": round(_sharpe(hedged), 2) if len(hedged) > 1 else None,
        "unhedged_sharpe": round(_sharpe(unhedged), 2) if len(unhedged) > 1 else None,
        "hedges": len(hedges),
        "hedges_that_cut": cut,
        "win_rate_pct": round(100 * cut / len(hedges)) if hedges else None,
        # Every hedge that was actually sent, graded or not. Orders placed is a
        # count of what this system did, not of what it is willing to be judged on.
        "hedges_ungraded": len(all_hedges) - len(hedges),
        "orders": len(all_hedges),
        "fees_bp_per_hedge": 11.3,
    }
