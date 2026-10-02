"""Re-grade settled hedges from the moment the hedge actually existed.

Settlement graded every hedge over the whole close-to-open window, as though the
perp short had been on from the closing bell. It never was. GitHub delays the
21:00Z cron and the 00:00Z backup fires instead, so the thirteen hedges on record
went on between 1.7 and 16.8 hours after the close - a median of 21% of the night
already gone, and on an earnings night the move lands in the first hour.

Grading the full window subtracts the perp leg from a fall the hedge was not there
for. On NKE 2026-10-01 that turned a 526 bp loss into a recorded 17 bp gain.

The ledger is append-only and hash-chained, so the seventeen signed settlements
are not edited. This appends the correction BESIDE them, under its own kind, the
same way the 2026-09-09 selector defect is carried. The page then shows the
corrected grade and names the superseded one.

The correction is reproducible rather than asserted: it is recomputed from the
signed decision's own `fill.at` and the venue's hourly candles, so anyone with
the ledger and the public candle endpoint derives the same rows.
"""
from __future__ import annotations

import argparse
import datetime as dt

from . import config
from .costs import HEDGE_COST_BP
from .ledger import Ledger
from .market import bars as market_bars
from .morning import _hedge_at, _settle_one
from .overnight import overnight_returns, split_returns
from .sessions import UTC

# Deep enough to reach the first graded night from any later run. Settlement uses
# 400 bars because it only ever prices last night; a re-grade has to price the
# whole record, and a window that silently fell short would drop exactly the
# oldest - worst-graded - nights from the correction.
REGRADE_BARS = 1400

REASON = ("settlement graded the full close-to-open window; this grades from the "
          "signed fill timestamp, so the hedge is credited only with the part of "
          "the night it was actually on")


def _bars(symbol: str, kind: str, cache: dict) -> dict[int, tuple[float, float]]:
    if (symbol, kind) not in cache:
        cache[(symbol, kind)] = market_bars(symbol, kind, max_bars=REGRADE_BARS,
                                            use_cache=False)
    return cache[(symbol, kind)]


def regrade_rows(decisions: list[dict], cache: dict | None = None) -> list[dict]:
    """Corrected rows for every HEDGE decision that can be priced on both legs.

    A row that cannot be split - no fill timestamp, a fill outside the window, a
    missing candle - is omitted rather than guessed. Omission leaves the original
    settlement standing and visible, which is the honest failure mode; a row
    silently graded on the full window again would not be.
    """
    cache = {} if cache is None else cache
    out = []
    for d in decisions:
        if d.get("action") != "HEDGE" or not d.get("session"):
            continue
        day = dt.date.fromisoformat(d["session"])
        at = _hedge_at(d)
        if at is None:
            continue
        spot, perp = d["spot_symbol"], d["perp_symbol"]
        spot_bars, perp_bars = _bars(spot, "spot", cache), _bars(perp, "mix", cache)
        spot_ret = overnight_returns(spot_bars).get(day)
        perp_ret = overnight_returns(perp_bars).get(day)
        if spot_ret is None or perp_ret is None:
            continue
        spot_split = split_returns(spot_bars, day, at)
        perp_split = split_returns(perp_bars, day, at)
        if not (spot_split and perp_split):
            continue
        row = _settle_one(d, spot_ret, perp_ret, HEDGE_COST_BP,
                          (*spot_split, *perp_split))
        row["session"] = d["session"]
        row["hedge_at"] = at.isoformat()
        out.append(row)
    return out


def run(session: str | None = None) -> dict:
    ledger = Ledger(config.LEDGER_PATH, config.secret())
    ledger.verify()

    settled = {s["body"].get("session") for s in ledger.records("settlement")}
    covered = {r.get("session")
               for e in ledger.records("regrade") for r in e["body"].get("rows", [])}

    decisions = [e["body"] for e in ledger.records("decision")
                 if e["body"].get("session") in settled
                 and e["body"].get("session") not in covered]
    if session:
        decisions = [d for d in decisions if d.get("session") == session]
    if not decisions:
        return {"regraded": 0, "note": "every settled session already has its correction"}

    rows = regrade_rows(decisions)
    if not rows:
        return {"regraded": 0, "note": "no settled hedge could be priced on both legs"}

    body = {
        "supersedes": "settlement",
        "reason": REASON,
        "bars": REGRADE_BARS,
        "sessions": sorted({r["session"] for r in rows}),
        "rows": rows,
    }
    ledger.append("regrade", body, dt.datetime.now(UTC))
    return {"regraded": len(rows), "sessions": body["sessions"], "rows": rows}


def brief(result: dict) -> str:
    if not result.get("regraded"):
        return f"Nothing to re-grade - {result.get('note', '')}."
    lines = [f"Re-graded {result['regraded']} hedges across "
             f"{len(result['sessions'])} sessions, from the signed fill timestamp.",
             f"  {'session':11s} {'tkr':5s} {'pre':>9s} {'post':>9s} "
             f"{'realised':>9s} {'value':>8s}  verdict"]
    for r in result["rows"]:
        lines.append(f"  {r['session']:11s} {r['ticker']:5s} {r['pre_hedge_bp']:9.1f} "
                     f"{r['post_hedge_bp']:9.1f} {r['realised_bp']:9.1f} "
                     f"{r['value_added_bp']:8.1f}  "
                     f"{'cut the move' if r['cut_the_move'] else 'did not cut'}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--session", help="re-grade one session only")
    args = ap.parse_args(argv)
    print(brief(run(args.session)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
