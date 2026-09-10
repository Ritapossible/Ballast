"""The morning run: settle every decision against what actually happened.

Ballast's strongest evidence property is that **every decision has an exact
counterfactual**. "What would have happened had we not hedged" is not modelled --
it is the observed rToken return over the same window. So both the hedges and the
refusals are graded, precisely, every morning.

Each row records the signed difference between the choice taken and the one
refused, and nothing more. A hedge also records whether it cut the move, which is
the symmetric question a single night can answer. A refusal records no verdict:
its value added is positive exactly when the position rose, so a nightly verdict
on a refusal would be a directional scorecard, and Ballast makes no directional
claim. Refusals are graded across the run, on the mean.

    python -m ballast.morning
"""
from __future__ import annotations

import argparse
import datetime as dt

from . import config
from .costs import HEDGE_COST_BP
from .ledger import Ledger
from .market import bars as market_bars
from .overnight import overnight_returns
from .universe import hedgeable_pairs
from .sessions import UTC

# Settlement grades a session against the following open, so it needs days of
# bars, not years. The default 12,000 pages back 60 times per symbol - 1,440
# requests for a twelve-position book, which is why a run took minutes. Two pages
# cover ~16 days, comfortably past the 14-day limit on how far back a session can
# still be outstanding.
SETTLE_BARS = 400


def _perp_for(spot_symbol: str) -> str:
    """Resolve the hedge leg from the live pair index rather than by string surgery.

    Older ledger entries predate `perp_symbol` being recorded, so this is the
    fallback for them. New decisions carry it explicitly.
    """
    for pair in hedgeable_pairs():
        if pair.spot == spot_symbol:
            return pair.perp
    raise ValueError(f"no perp leg for {spot_symbol}")


def _settle_one(record: dict, spot_ret: float, perp_ret: float,
                cost_bp: float = HEDGE_COST_BP) -> dict:
    """Grade one decision against the outcome of the choice NOT taken.

    Both branches are scored the same way, which is the only way a refusal can be
    graded honestly:

        hedged      realised = spot - perp - cost   counterfactual = spot
        not hedged  realised = spot                 counterfactual = spot - perp - cost

    `value_added_bp` is the SIGNED profit-and-loss difference between the choice
    taken and the one refused. Signed, not absolute: a hedge almost always shrinks
    the move (beta is ~1.00), so scoring on size alone would say "always hedge" -
    which is precisely the policy the research rejected, because it cost ~13% a
    year. Protection is insurance, and insurance pays off when the loss actually
    arrives. So hedging wins on a night that fell, and declining wins on a night
    that rose or stayed flat.

    The earlier definition compared |move| against the 12 bp cost on every night.
    Because typical overnight moves are 100-400 bp, it marked essentially every
    refusal wrong - and the policy declines roughly 90% of position-nights.

    No per-row correct/wrong is stored. Both replacements for that flag were
    directional in disguise: value_added_bp > 0 on a refusal says only that the
    position rose. A hedge does get a verdict, because "did it cut the move" is
    symmetric and one night settles it.
    """
    unhedged_bp = spot_ret * 1e4
    protected_bp = (spot_ret - perp_ret) * 1e4 - cost_bp
    hedged = record["action"] == "HEDGE"

    realised_bp = protected_bp if hedged else unhedged_bp
    counterfactual_bp = unhedged_bp if hedged else protected_bp
    value_added_bp = realised_bp - counterfactual_bp

    return {
        "ticker": record["ticker"],
        "action": record["action"],
        "unhedged_bp": round(unhedged_bp, 1),
        "realised_bp": round(realised_bp, 1),
        "counterfactual_bp": round(counterfactual_bp, 1),
        "value_added_bp": round(value_added_bp, 1),
        "cut_the_move": abs(protected_bp) < abs(unhedged_bp) if hedged else None,
        "cost_bp": round(cost_bp, 1),
        "rationale": record.get("rationale", ""),
        "event": record.get("event", {}).get("type"),
    }


def run(session: str | None = None) -> dict:
    ledger = Ledger(config.LEDGER_PATH, config.secret())
    ledger.verify()                                    # refuse to settle a broken chain

    decisions = [e["body"] for e in ledger.records("decision")]
    already = {e["body"].get("session") for e in ledger.records("settlement")}

    if session:
        # Idempotent by construction: settling the same session twice would append
        # a second record, and the site flattens every settlement into one list -
        # so the tiles would double-count.
        if session in already:
            return {"settled": 0, "note": f"{session} is already settled"}
        decisions = [d for d in decisions if d.get("session") == session]
    else:
        decisions = [d for d in decisions
                     if d.get("session") and d["session"] not in already]
    if not decisions:
        return {"settled": 0, "note": "nothing outstanding"}

    cost_bp = HEDGE_COST_BP
    by_session: dict[str, list[dict]] = {}
    for d in decisions:
        by_session.setdefault(d["session"], []).append(d)

    out: dict = {"sessions": {}}
    now = dt.datetime.now(UTC)
    for sess, rows in sorted(by_session.items()):
        day = dt.date.fromisoformat(sess)
        graded, ungraded = [], []
        for r in rows:
            perp = r.get("perp_symbol") or _perp_for(r["spot_symbol"])
            # use_cache=False, as at night. The cache never expires, so a second
            # settlement on a machine that had already fetched these symbols would
            # grade tonight's decision against an older session's bars.
            spot_ret = overnight_returns(market_bars(
                r["spot_symbol"], "spot", max_bars=SETTLE_BARS, use_cache=False)).get(day)
            perp_ret = overnight_returns(market_bars(
                perp, "mix", max_bars=SETTLE_BARS, use_cache=False)).get(day)
            if spot_ret is None or perp_ret is None:
                ungraded.append(r["ticker"])           # window not closed, or a data gap
                continue
            graded.append(_settle_one(r, spot_ret, perp_ret, cost_bp))

        if not graded:
            continue
        if ungraded:
            # Writing a settlement marks the session done, and outstanding sessions
            # are found by "has no settlement record" - so settling partially would
            # strand these decisions permanently. Wait for the whole session instead.
            out.setdefault("deferred", {})[sess] = ungraded
            continue
        summary = {
            "session": sess,
            "decisions": len(graded),
            "hedged": sum(1 for g in graded if g["action"] == "HEDGE"),
            "hedges_that_cut": sum(1 for g in graded if g.get("cut_the_move")),
            "worst_unhedged_bp": max((abs(g["unhedged_bp"]) for g in graded), default=0),
            "worst_realised_bp": max((abs(g["realised_bp"]) for g in graded), default=0),
            "net_value_added_bp": round(sum(g["value_added_bp"] for g in graded), 1),
            "rows": graded,
        }
        ledger.append("settlement", summary, now)
        out["sessions"][sess] = summary

    out["settled"] = sum(s["decisions"] for s in out["sessions"].values())
    return out


def _verdict(row: dict) -> str:
    """Only a hedge gets one. See _settle_one."""
    if row["action"] != "HEDGE":
        return "carried"
    return "cut the move" if row.get("cut_the_move") else "did not cut"


def brief(result: dict) -> str:
    if not result.get("sessions"):
        return "Nothing to settle - no overnight window has closed since the last run."
    lines = []
    for sess, s in result["sessions"].items():
        lines.append(f"\n  {sess} - {s['decisions']} decisions, {s['hedged']} hedged, "
                     f"{s['hedges_that_cut']}/{s['hedged']} hedges cut the move")
        lines.append(f"  {'ticker':8s} {'action':10s} {'unhedged':>10s} {'realised':>10s} "
                     f"{'value':>8s}  verdict")
        lines.append("  " + "-" * 62)
        for g in sorted(s["rows"], key=lambda r: -abs(r["unhedged_bp"])):
            lines.append(f"  {g['ticker']:8s} {g['action']:10s} {g['unhedged_bp']:9.0f}bp "
                         f"{g['realised_bp']:9.0f}bp {g['value_added_bp']:7.0f}bp  "
                         f"{_verdict(g)}")
        lines.append(f"  worst night: {s['worst_unhedged_bp']:.0f}bp unhedged -> "
                     f"{s['worst_realised_bp']:.0f}bp realised · "
                     f"net {s['net_value_added_bp']:+.0f}bp")
    return "\n".join(lines)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--session", help="settle one session (YYYY-MM-DD)")
    print(brief(run(**vars(ap.parse_args()))))
