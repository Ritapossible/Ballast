"""US earnings calendar, from Nasdaq's public calendar endpoint.

Gate 1 measured that trailing realised volatility cannot find the nights worth
hedging (1.41x separation, versus 13.2x when the same nights are chosen with
hindsight). Overnight equity variance is driven by SCHEDULED events, so the
selector has to be a calendar. This module is that calendar.

Endpoint: https://api.nasdaq.com/api/calendar/earnings?date=YYYY-MM-DD
Returns every company reporting on that date. Works for past dates, which is what
the historical study needs. Requires a browser User-Agent.

Known limitation: the `time` field (time-pre-market / time-after-hours) is
populated for upcoming dates but degrades to `time-not-supplied` for past ones.
Both cases fall inside our close->open window, so the date alone is sufficient for
selection; the flag is used when present to describe the event, never to gate it.
"""
from __future__ import annotations

import datetime as dt
import json
import time
import urllib.error
import urllib.request
from pathlib import Path

from .sessions import next_session

# Sessions decided before `scheduled_in_window` checked the release time. The old
# rule ORed the two calendar dates, so it could turn a NO_HEDGE into a HEDGE and
# never the reverse - which is why only hedges on these sessions are marked.
# Anything reading the record has to be able to say which nights that touched, so
# the list lives beside the rule it corrects rather than in a page builder.
SELECTOR_BUG_SESSIONS = frozenset({"2026-09-09"})

CACHE = Path(__file__).resolve().parent.parent / ".cache" / "earnings"
_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
_ENDPOINT = "https://api.nasdaq.com/api/calendar/earnings?date={}"
_PACE_SECONDS = 0.4


def _fetch_day(day: dt.date, retries: int = 3) -> list[dict]:
    cache_file = CACHE / f"{day.isoformat()}.json"
    if cache_file.exists():
        return json.loads(cache_file.read_text())

    req = urllib.request.Request(
        _ENDPOINT.format(day.isoformat()),
        headers={"User-Agent": _UA, "Accept": "application/json"},
    )
    rows: list[dict] = []
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                payload = json.load(resp)
            rows = (payload.get("data") or {}).get("rows") or []
            break
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
            if attempt == retries - 1:
                return []          # a missing day is absence of evidence, not zero earnings
            time.sleep(2 ** attempt)

    slim = [{"symbol": r.get("symbol"), "time": r.get("time")} for r in rows if r.get("symbol")]
    CACHE.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(json.dumps(slim))
    time.sleep(_PACE_SECONDS)
    return slim


def symbols_on(day: dt.date) -> dict[str, str]:
    """{ticker: time_flag} for every company reporting on `day`."""
    return {r["symbol"]: r.get("time") or "time-not-supplied" for r in _fetch_day(day)}


def scheduled_in_window(ticker: str, session: dt.date) -> str | None:
    """The flag for a report that actually falls inside this session's window.

    Nasdaq lists a report under the calendar date it is released, and the window
    runs from `session`'s close to the next session's open. So:

        session, after-hours      inside   <- the common case
        session, pre-market       OUTSIDE  - it happened before this close
        next session, pre-market  inside
        next session, after-hours OUTSIDE  - the window shut hours earlier

    The old rule ORed the two dates and ignored the flag, so an after-hours report
    on the next session hedged the night before as well as the night itself: two
    nights of cost per event, one of them protecting nothing. That is how the
    2026-09-09 session came to hedge ORCL, whose earnings were the following night.

    `time-not-supplied` passes both gates. Nasdaq only populates the flag for
    upcoming dates, so historical dates are matched on date alone - which is the
    rule the Gate 1 study measured, and keeps this consistent with it.
    """
    flag = symbols_on(session).get(ticker)
    if flag and flag != "time-pre-market":
        return flag
    flag = symbols_on(next_session(session)).get(ticker)
    if flag and flag != "time-after-hours":
        return flag
    return None


def build_calendar(start: dt.date, end: dt.date, tickers: set[str] | None = None
                   ) -> dict[str, set[dt.date]]:
    """{ticker: {report dates}} over [start, end], weekdays only."""
    out: dict[str, set[dt.date]] = {}
    day = start
    while day <= end:
        if day.weekday() <= 4:
            for sym, _ in symbols_on(day).items():
                if tickers is None or sym in tickers:
                    out.setdefault(sym, set()).add(day)
        day += dt.timedelta(days=1)
    return out


def coverage(start: dt.date, end: dt.date) -> tuple[int, int]:
    """(days cached, weekdays in range) — how complete the crawl is."""
    weekdays = sum(1 for d in _dates(start, end) if d.weekday() <= 4)
    cached = sum(1 for d in _dates(start, end)
                 if d.weekday() <= 4 and (CACHE / f"{d.isoformat()}.json").exists())
    return cached, weekdays


def _dates(start: dt.date, end: dt.date):
    day = start
    while day <= end:
        yield day
        day += dt.timedelta(days=1)


if __name__ == "__main__":
    import sys
    start = dt.date.fromisoformat(sys.argv[1]) if len(sys.argv) > 1 else dt.date(2025, 10, 1)
    end = dt.date.fromisoformat(sys.argv[2]) if len(sys.argv) > 2 else dt.date.today()
    cal = build_calendar(start, end)
    done, total = coverage(start, end)
    print(f"crawled {done}/{total} weekdays · {len(cal)} tickers with >=1 report")
    for t in ["NVDA", "TSLA", "AAPL", "MSFT", "AMZN", "META", "GOOGL",
              "COIN", "PLTR", "AMD", "ORCL", "ADBE", "MU", "NKE", "COST"]:
        days = sorted(cal.get(t, []))
        print(f"  {t:6s} {len(days)} reports: {', '.join(d.isoformat() for d in days)}")
