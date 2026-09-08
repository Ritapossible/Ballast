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

from sessions import UTC, overnight_window, sessions_between

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


def overnight_returns(bars: dict[int, tuple[float, float]] | dict[int, float]
                      ) -> dict[dt.date, float]:
    """{session_date: log return, that session's close -> the next session's open}.

    Accepts either {ts: (open, close)} or {ts: close}; with closes only, the open
    leg falls back to the preceding bar's close, which is the same instant.
    Friday yields the Friday-close -> Monday-open window.
    """
    if not bars:
        return {}
    normalised: dict[int, tuple[float, float]] = {
        ts: (v if isinstance(v, tuple) else (v, v)) for ts, v in bars.items()
    }
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


def aligned(a: dict[dt.date, float], b: dict[dt.date, float]):
    """Paired series over the dates both cover — (dates, a_values, b_values)."""
    dates = sorted(set(a) & set(b))
    return dates, [a[d] for d in dates], [b[d] for d in dates]
