"""US exchange holidays and early closes, computed rather than tabulated.

The session calendar previously treated every weekday as a trading day. A holiday
therefore produced a window spanning an extra closed day - a Thursday-close to
Monday-open window mislabelled as a normal 17.5-hour overnight - which understates
the exposure being priced on exactly the nights when it is largest.

Rules rather than a hardcoded table, so the calendar does not expire. Sources: NYSE
Rule 7.2 (holidays) and the exchange's published early-close schedule.
"""
from __future__ import annotations

import datetime as dt
import functools

# 13:00 ET rather than 16:00 on the sessions before Independence Day, the day after
# Thanksgiving, and Christmas Eve.
EARLY_CLOSE = dt.time(13, 0)


def easter(year: int) -> dt.date:
    """Anonymous Gregorian algorithm. Good Friday is the only movable feast the
    exchange observes, and it does not follow a weekday rule."""
    a, b, c = year % 19, year // 100, year % 100
    d, e = b // 4, b % 4
    g = (b - (b + 8) // 25 + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    lm = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * lm) // 451
    month = (h + lm - 7 * m + 114) // 31
    day = ((h + lm - 7 * m + 114) % 31) + 1
    return dt.date(year, month, day)


def _nth_weekday(year: int, month: int, weekday: int, n: int) -> dt.date:
    first = dt.date(year, month, 1)
    offset = (weekday - first.weekday()) % 7
    return first + dt.timedelta(days=offset + 7 * (n - 1))


def _last_weekday(year: int, month: int, weekday: int) -> dt.date:
    nxt = dt.date(year + (month == 12), month % 12 + 1, 1)
    last = nxt - dt.timedelta(days=1)
    return last - dt.timedelta(days=(last.weekday() - weekday) % 7)


def _observed(day: dt.date) -> dt.date | None:
    """A fixed-date holiday falling at a weekend moves. A Saturday holiday is
    observed the Friday before, a Sunday one the Monday after - except a Saturday
    1 January, which the exchange does not observe at all."""
    if day.weekday() == 5:
        if (day.month, day.day) == (1, 1):
            return None
        return day - dt.timedelta(days=1)
    if day.weekday() == 6:
        return day + dt.timedelta(days=1)
    return day


@functools.lru_cache(maxsize=32)
def holidays(year: int) -> frozenset[dt.date]:
    """Full-day closures observed by the NYSE in `year`."""
    fixed = [dt.date(year, 1, 1), dt.date(year, 7, 4), dt.date(year, 12, 25)]
    if year >= 2022:
        fixed.append(dt.date(year, 6, 19))          # Juneteenth, from 2022
    days = {_observed(d) for d in fixed}
    days |= {
        _nth_weekday(year, 1, 0, 3),                # MLK Day
        _nth_weekday(year, 2, 0, 3),                # Washington's Birthday
        easter(year) - dt.timedelta(days=2),        # Good Friday
        _last_weekday(year, 5, 0),                  # Memorial Day
        _nth_weekday(year, 9, 0, 1),                # Labor Day
        _nth_weekday(year, 11, 3, 4),               # Thanksgiving
    }
    return frozenset(d for d in days if d is not None)


@functools.lru_cache(maxsize=32)
def early_closes(year: int) -> frozenset[dt.date]:
    """Sessions closing at 13:00 ET."""
    days = set()
    for candidate in (dt.date(year, 7, 3),                              # before July 4
                      _nth_weekday(year, 11, 3, 4) + dt.timedelta(days=1),  # after Thanksgiving
                      dt.date(year, 12, 24)):                           # Christmas Eve
        if candidate.weekday() <= 4 and candidate not in holidays(year):
            days.add(candidate)
    return frozenset(days)


def is_holiday(day: dt.date) -> bool:
    return day in holidays(day.year)


def is_trading_day(day: dt.date) -> bool:
    return day.weekday() <= 4 and not is_holiday(day)


def closes_early(day: dt.date) -> bool:
    return day in early_closes(day.year)
