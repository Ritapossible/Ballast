"""The morning run: settle every decision against what actually happened.

Ballast's strongest evidence property is that **every decision has an exact
counterfactual**. "What would have happened had we not hedged" is not modelled --
it is the observed rToken return over the same window. So both the hedges and the
refusals are graded, precisely, every morning.

A decision is scored correct when it was the cheaper choice ex post:

    HEDGED    and |unhedged move| > cost  -> correct (protection paid for itself)
    NOT HEDGED and |unhedged move| < cost -> correct (the fee was rightly saved)

    python -m ballast.morning
"""
from __future__ import annotations

import argparse
import datetime as dt

from . import config
from .executor import PERP_TAKER_FEE
from .ledger import Ledger
from .market import closes
from .overnight import overnight_returns
from .sessions import UTC


def _settle_one(record: dict, spot_ret: float, perp_ret: float,
                cost_bp: float) -> dict:
    """Grade one decision. Returns are logs over the same overnight window."""
    unhedged_bp = spot_ret * 1e4
    hedged = record["action"] == "HEDGE"
    # A short perp against long spot: residual = spot - perp, less round-trip cost.
    residual_bp = (spot_ret - perp_ret) * 1e4 - cost_bp if hedged else unhedged_bp
    value_added_bp = abs(unhedged_bp) - abs(residual_bp)
    correct = (abs(unhedged_bp) > cost_bp) if hedged else (abs(unhedged_bp) <= cost_bp)
    return {
        "ticker": record["ticker"],
        "action": record["action"],
        "unhedged_bp": round(unhedged_bp, 1),
        "realised_bp": round(residual_bp, 1),
        "value_added_bp": round(value_added_bp, 1),
        "correct": correct,
        "rationale": record.get("rationale", ""),
        "event": record.get("event", {}).get("type"),
    }


def run(session: str | None = None) -> dict:
    ledger = Ledger(config.LEDGER_PATH, config.secret())
    ledger.verify()                                    # refuse to settle a broken chain

    decisions = [e["body"] for e in ledger.records("decision")]
    if session:
        decisions = [d for d in decisions if d.get("session") == session]
    else:
        settled = {e["body"].get("session") for e in ledger.records("settlement")}
        decisions = [d for d in decisions
                     if d.get("session") and d["session"] not in settled]
    if not decisions:
        return {"settled": 0, "note": "nothing outstanding"}

    cost_bp = PERP_TAKER_FEE * 2 * 1e4                 # round trip, taker both ways
    by_session: dict[str, list[dict]] = {}
    for d in decisions:
        by_session.setdefault(d["session"], []).append(d)

    out: dict = {"sessions": {}}
    now = dt.datetime.now(UTC)
    for sess, rows in sorted(by_session.items()):
        day = dt.date.fromisoformat(sess)
        graded = []
        for r in rows:
            perp = r["spot_symbol"][1:]                # RTSLAUSDT -> TSLAUSDT
            spot_ret = overnight_returns(closes(r["spot_symbol"], "spot")).get(day)
            perp_ret = overnight_returns(closes(perp, "mix")).get(day)
            if spot_ret is None or perp_ret is None:
                continue                               # window has not closed yet
            graded.append(_settle_one(r, spot_ret, perp_ret, cost_bp))

        if not graded:
            continue
        summary = {
            "session": sess,
            "decisions": len(graded),
            "correct": sum(1 for g in graded if g["correct"]),
            "hedged": sum(1 for g in graded if g["action"] == "HEDGE"),
            "worst_unhedged_bp": max((abs(g["unhedged_bp"]) for g in graded), default=0),
            "worst_realised_bp": max((abs(g["realised_bp"]) for g in graded), default=0),
            "net_value_added_bp": round(sum(g["value_added_bp"] for g in graded), 1),
            "rows": graded,
        }
        ledger.append("settlement", summary, now)
        out["sessions"][sess] = summary

    out["settled"] = sum(s["decisions"] for s in out["sessions"].values())
    return out


def brief(result: dict) -> str:
    if not result.get("sessions"):
        return "Nothing to settle — no overnight window has closed since the last run."
    lines = []
    for sess, s in result["sessions"].items():
        lines.append(f"\n  {sess} — {s['decisions']} decisions, {s['hedged']} hedged, "
                     f"{s['correct']}/{s['decisions']} correct")
        lines.append(f"  {'ticker':8s} {'action':10s} {'unhedged':>10s} {'realised':>10s} "
                     f"{'value':>8s}  verdict")
        lines.append("  " + "-" * 62)
        for g in sorted(s["rows"], key=lambda r: -abs(r["unhedged_bp"])):
            lines.append(f"  {g['ticker']:8s} {g['action']:10s} {g['unhedged_bp']:9.0f}bp "
                         f"{g['realised_bp']:9.0f}bp {g['value_added_bp']:7.0f}bp  "
                         f"{'correct' if g['correct'] else 'wrong'}")
        lines.append(f"  worst night: {s['worst_unhedged_bp']:.0f}bp unhedged -> "
                     f"{s['worst_realised_bp']:.0f}bp realised · "
                     f"net {s['net_value_added_bp']:+.0f}bp")
    return "\n".join(lines)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--session", help="settle one session (YYYY-MM-DD)")
    print(brief(run(**vars(ap.parse_args()))))
