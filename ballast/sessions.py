"""US equity session calendar, DST-correct.

The single source of truth for "when is the US primary market closed".
Nothing else in this codebase may hardcode an hour: the US close is 20:00 UTC
under EDT and 21:00 UTC under EST, and our data sample spans both.

DST transitions inside the sample: 2025-11-02 (EDT->EST), 2026-03-08 (EST->EDT).
"""
from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

from .holidays import closes_early, is_trading_day

NY = ZoneInfo("America/New_York")
UTC = ZoneInfo("UTC")

MARKET_OPEN = dt.time(9, 30)
MARKET_CLOSE = dt.time(16, 0)
EARLY_CLOSE = dt.time(13, 0)


def _ny(date: dt.date, t: dt.time) -> dt.datetime:
    return dt.datetime.combine(date, t, tzinfo=NY)


def close_utc(session: dt.date) -> dt.datetime:
    """UTC instant of the close for a session - 13:00 ET on an early-close day."""
    hour = EARLY_CLOSE if closes_early(session) else MARKET_CLOSE
    return _ny(session, hour).astimezone(UTC)


def open_utc(session: dt.date) -> dt.datetime:
    """UTC instant of the 09:30 ET open for a given session date."""
    return _ny(session, MARKET_OPEN).astimezone(UTC)


MAX_SESSION_LOOKBACK_DAYS = 14


def current_session(now: dt.datetime) -> dt.date:
    """The most recent session whose close has already passed.

    This picks the day the whole loop then trades and grades, so it has to agree
    with the rest of the calendar. It tested `weekday() <= 4` while every other
    function here uses is_trading_day, so on Thanksgiving it returned Thanksgiving:
    a session the exchange never opened, priced against a window that never existed.
    next_session had skipped that same holiday correctly, so the two disagreed.

    Bounded: an unbounded backward walk would spin forever on a clock or calendar
    fault rather than failing where it can be seen.
    """
    day = now.date()
    for _ in range(MAX_SESSION_LOOKBACK_DAYS):
        if is_trading_day(day) and now >= close_utc(day):
            return day
        day -= dt.timedelta(days=1)
    raise RuntimeError(
        f"no closed session found within {MAX_SESSION_LOOKBACK_DAYS} days of {now}")


def next_session(session: dt.date) -> dt.date:
    """The next day the exchange is actually open.

    Holidays are skipped, not just weekends. Treating a holiday as a trading day
    produced a window that silently spanned an extra closed day - understating the
    exposure being priced on precisely the nights when it is longest.
    """
    nxt = session + dt.timedelta(days=1)
    for _ in range(10):                      # bounded: no run of closures is longer
        if is_trading_day(nxt):
            return nxt
        nxt += dt.timedelta(days=1)
    raise RuntimeError(f"no trading day within 10 days of {session}")


def overnight_window(session: dt.date) -> tuple[dt.datetime, dt.datetime]:
    """(close of `session`, open of the following session), both UTC.

    Friday returns the Friday-close -> Monday-open window, which is the longest
    and highest-exposure window of the week.
    """
    return close_utc(session), open_utc(next_session(session))


def window_hours(session: dt.date) -> float:
    a, b = overnight_window(session)
    return (b - a).total_seconds() / 3600.0


def sessions_between(start: dt.date, end: dt.date):
    """Trading sessions in [start, end] - weekdays the exchange was open."""
    d = start
    while d <= end:
        if is_trading_day(d):
            yield d
        d += dt.timedelta(days=1)

