"""Which recent trading sessions have no decision on the chain.

    python3 tools/check_coverage.py [--days 10]

A scheduled run that never fires leaves a hole the paper log cannot backfill: the
decide half is graded on being written before the outcome is known, so it cannot
be reconstructed afterwards. Nothing checked that a run had actually landed - the
workflow reported success for starting, not for producing anything.

Needs no signing key. Coverage is a question about which sessions appear, and
reading the chain's structure does not require verifying its signatures.
"""
from __future__ import annotations

import argparse
import datetime as dt
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ballast import config
from ballast.holidays import is_trading_day
from ballast.ledger import Ledger
from ballast.report import DECIDE_GRACE_HOURS
from ballast.sessions import UTC, close_utc


def missing(days: int, now: dt.datetime | None = None) -> list[dt.date]:
    """Trading sessions whose decide run was due and never appeared."""
    now = now or dt.datetime.now(UTC)
    if not config.LEDGER_PATH.exists():
        return []
    decided = {e["body"].get("session")
               for e in Ledger(config.LEDGER_PATH, config.DEV_SECRET)
               .records("night_summary")}
    # A chain starts when it starts: sessions before the first entry were never
    # this deployment's to decide, and reporting them as holes is noise.
    earliest = min((s for s in decided if s), default=None)

    out = []
    for back in range(days):
        day = now.date() - dt.timedelta(days=back)
        if not is_trading_day(day):
            continue
        # Only count it once the run was actually overdue, on the same clock the
        # site uses to decide whether it is stale.
        if now < close_utc(day) + dt.timedelta(hours=DECIDE_GRACE_HOURS):
            continue
        iso = day.isoformat()
        if earliest and iso < earliest:
            continue
        if iso not in decided:
            out.append(day)
    return sorted(out)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--days", type=int, default=10)
    holes = missing(ap.parse_args().days)
    if not holes:
        print("coverage complete: every due session has a decision on the chain")
        raise SystemExit(0)
    print("MISSING DECISIONS - these nights cannot be recovered:")
    for day in holes:
        print(f"  {day} (close {close_utc(day):%Y-%m-%d %H:%M}Z)")
    raise SystemExit(1)
