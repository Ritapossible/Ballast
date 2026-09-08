"""US equity session calendar, DST-correct.

The single source of truth for "when is the US primary market closed".
Nothing else in this codebase may hardcode an hour: the US close is 20:00 UTC
under EDT and 21:00 UTC under EST, and our data sample spans both.

DST transitions inside the sample: 2025-11-02 (EDT->EST), 2026-03-08 (EST->EDT).
"""
from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

NY = ZoneInfo("America/New_York")
UTC = ZoneInfo("UTC")

MARKET_OPEN = dt.time(9, 30)
MARKET_CLOSE = dt.time(16, 0)


def _ny(date: dt.date, t: dt.time) -> dt.datetime:
    return dt.datetime.combine(date, t, tzinfo=NY)


def close_utc(session: dt.date) -> dt.datetime:
    """UTC instant of the 16:00 ET close for a given session date."""
    return _ny(session, MARKET_CLOSE).astimezone(UTC)


def open_utc(session: dt.date) -> dt.datetime:
    """UTC instant of the 09:30 ET open for a given session date."""
    return _ny(session, MARKET_OPEN).astimezone(UTC)


def next_session(session: dt.date) -> dt.date:
    """Next weekday. Exchange holidays are NOT handled — see caveat below."""
    nxt = session + dt.timedelta(days=1)
    while nxt.weekday() > 4:
        nxt += dt.timedelta(days=1)
    return nxt


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
    """Weekday sessions in [start, end]."""
    d = start
    while d <= end:
        if d.weekday() <= 4:
            yield d
        d += dt.timedelta(days=1)


# CAVEAT (tracked, not yet fixed): US exchange holidays are not modelled. A holiday
# produces a window that spans an extra closed day and is therefore mislabelled as a
# normal overnight. Affects window length, not the hedge relationship. Fix before
# publishing per-window 1-sigma figures.
