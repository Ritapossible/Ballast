"""Which overnight window a bar falls in, as pure arithmetic.

Split out of the strategy so it can be tested without the Nautilus runtime.
The replay decides whether to be short from the bar's own timestamp, so this is
the whole selector - if it is wrong, every trade is wrong, and it is the one
part of the package that can be checked offline.
"""
import datetime as dt

# US cash session in UTC during EDT. The competition window ends before the
# 2026-11-01 fallback, so a fixed offset is correct and a DST conversion would
# add a dependency without changing a single bar.
CLOSE_UTC_HOUR = 20
OPEN_UTC_HOUR = 13
OPEN_UTC_MINUTE = 30


def inside_window(when):
    """True when the market that prices the underlying is shut."""
    if when.hour >= CLOSE_UTC_HOUR:
        return True
    return (when.hour, when.minute) < (OPEN_UTC_HOUR, OPEN_UTC_MINUTE)


def protected_night(when):
    """The session whose close opened the window containing `when`.

    A bar at or after the close belongs to that day's night. A bar before the
    opening bell belongs to the previous weekday's night - so Monday 02:00
    belongs to Friday, not to Sunday.
    """
    if when.hour >= CLOSE_UTC_HOUR:
        return when.date()
    session = when.date() - dt.timedelta(days=1)
    while session.weekday() > 4:
        session -= dt.timedelta(days=1)
    return session


def should_protect(symbol, when, event_dates):
    """Short only inside a window, and only on a night the calendar flagged.

    An empty mapping protects every night: the indiscriminate baseline the
    research rejects, kept reachable so the comparison can be run rather than
    asserted.
    """
    if not inside_window(when):
        return False
    if not event_dates:
        return True
    wanted = event_dates.get(symbol)
    return bool(wanted) and protected_night(when).isoformat() == wanted
