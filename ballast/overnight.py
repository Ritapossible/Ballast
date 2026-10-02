"""Overnight return series, built on the DST-correct session calendar.

One subtlety worth stating plainly: the 16:00 ET close lands on an exact hourly
boundary (20:00Z / 21:00Z) but the 09:30 ET open does not (13:30Z / 14:30Z).
Hourly candles are stamped at the bar's START, so the open is snapped UP to the
next whole hour and we take that bar's OPEN price -- 10:00 ET, thirty minutes
into the primary session. That is a real, liquid, post-auction price, and using
it consistently on both legs keeps the comparison exact.
"""
from __future__ import annotations

import datetime as dt
import math

from .sessions import UTC, overnight_window, sessions_between

HOUR_MS = 3_600_000


def _floor_hour_ms(when: dt.datetime) -> int:
    return int(when.replace(minute=0, second=0, microsecond=0).timestamp() * 1000)


def _ceil_hour_ms(when: dt.datetime) -> int:
    floored = when.replace(minute=0, second=0, microsecond=0)
    if when != floored:
        floored += dt.timedelta(hours=1)
    return int(floored.timestamp() * 1000)


def _lookup(bars: dict[int, tuple[float, float]], ts: int, field: int,
            tol_hours: int = 2) -> float | None:
    """Price at bar `ts`, tolerating short gaps in the candle series."""
    for offset in range(tol_hours + 1):
        for step in ((0,) if offset == 0 else (offset, -offset)):
            bar = bars.get(ts + step * HOUR_MS)
            if bar and bar[field] > 0:
                return bar[field]
    return None


class BarFormatError(TypeError):
    """Close-only input was passed where open/close bars are required."""


def overnight_returns(bars: dict[int, tuple[float, float]]) -> dict[dt.date, float]:
    """{session_date: log return, that session's close -> the next session's open}.

    Requires {ts: (open, close)} from `market.bars()`. Close-only input is REFUSED
    rather than silently degraded: with closes alone the open leg resolves to the
    previous hour's close, which shifted returns by a mean of 71-99 bp per night
    and inflated sigma by ~15% against the research definition. A production
    surface quietly disagreeing with the research that justifies it is worse than
    a crash, so this raises.

    Friday yields the Friday-close -> Monday-open window.
    """
    if not bars:
        return {}
    sample = next(iter(bars.values()))
    if not isinstance(sample, tuple):
        raise BarFormatError(
            "overnight_returns requires {ts: (open, close)} from market.bars(); "
            "market.closes() loses the open leg and shifts every return")
    normalised: dict[int, tuple[float, float]] = dict(bars)
    stamps = sorted(normalised)
    first = dt.datetime.fromtimestamp(stamps[0] / 1000, UTC).date()
    last = dt.datetime.fromtimestamp(stamps[-1] / 1000, UTC).date()

    out: dict[dt.date, float] = {}
    for session in sessions_between(first, last):
        close_at, open_at = overnight_window(session)
        start = _lookup(normalised, _floor_hour_ms(close_at), field=1)   # bar close
        end = _lookup(normalised, _ceil_hour_ms(open_at), field=0)       # bar open
        if start and end:
            out[session] = math.log(end / start)
    return out


def split_returns(bars: dict[int, tuple[float, float]], session: dt.date,
                  at: dt.datetime) -> tuple[float, float] | None:
    """One session's overnight return, cut in two at `at`: (before, after).

    A hedge placed after the close only protects the part of the night that
    follows it, and this project's hedges are routinely late - GitHub delays the
    21:00Z cron and the 00:00Z backup fires instead, four hours past the close.
    Grading the whole window as if the hedge had been on throughout subtracts the
    perp leg from a move the hedge was not there for. On NKE 2026-10-01 that
    turned a 506 bp loss into a recorded 17 bp gain.

    Both legs are priced off the SAME mid-window bar, so before + after is exactly
    overnight_returns()[session] - log returns add. A test pins that identity,
    because a split that does not sum back is a second definition of the night.

    Returns None when a leg is missing, for the same reason overnight_returns
    skips a session it cannot price on both ends.
    """
    close_at, open_at = overnight_window(session)
    if not close_at <= at <= open_at:
        return None
    start = _lookup(bars, _floor_hour_ms(close_at), field=1)
    # tol_hours=0, unlike the two ends: _lookup will otherwise fetch a bar up to
    # two hours either side, which silently moves the hedge by up to two hours.
    # On an earnings night the whole move is in the first hour after the close, so
    # a cut shifted an hour is a different night. A missing candle at the fill hour
    # means this night cannot be split, and regrade_rows leaves the original
    # settlement standing and visible rather than re-pricing it on a nearby bar.
    mid = _lookup(bars, _floor_hour_ms(at), field=1, tol_hours=0)
    end = _lookup(bars, _ceil_hour_ms(open_at), field=0)
    if not (start and mid and end):
        return None
    return math.log(mid / start), math.log(end / mid)


def aligned(a: dict[dt.date, float], b: dict[dt.date, float]):
    """Paired series over the dates both cover — (dates, a_values, b_values)."""
    dates = sorted(set(a) & set(b))
    return dates, [a[d] for d in dates], [b[d] for d in dates]
