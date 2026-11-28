"""When the workflow's decide triggers actually fire, read from the workflow.

check_coverage waited a flat four hours after the close before calling a session
missing. That is right only while the last decide trigger lands within four hours
of the close - true for a normal 21:00Z close, where the last chance is 00:00Z,
and false the moment the close moves.

On 2026-11-27, the half day after Thanksgiving, the US close was 18:00Z. The last
decide trigger was still 00:00Z, six hours later, so the gate called the night
missing at 22:51Z - two hours before its final chance had even fired - and failed
the job. The session was decided shortly afterwards, exactly as the backups are
meant to arrange. The schedule was fine; the thing measuring it was guessing.

So the deadline is derived from the schedule itself rather than from a constant
that happens to suit one close. Stdlib only, like the rest of the package: the
crons are read out of the workflow with a regex rather than a YAML parser.
"""
from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path

from .sessions import UTC, close_utc, overnight_window

WORKFLOW = Path(__file__).resolve().parent.parent / ".github/workflows/nightly.yml"

# A decision written after half the window has gone is refused by night.run(), so
# a trigger past that point is not a chance to decide this session at all.
MAX_WINDOW_ELAPSED = 0.5

# Cron counts Sunday as 0; datetime.weekday() counts Monday as 0.
_CRON_DOW = {0: 6, 1: 0, 2: 1, 3: 2, 4: 3, 5: 4, 6: 5}


def _dow_matches(field: str, day: dt.date) -> bool:
    want = {d for d in range(7) if _CRON_DOW[d] == day.weekday()}
    if field == "*":
        return True
    for part in field.split(","):
        if "-" in part:
            lo, hi = (int(x) for x in part.split("-"))
            if any(lo <= d <= hi for d in want):
                return True
        elif int(part) in want:
            return True
    return False


def decide_crons(workflow: Path | None = None) -> list[str]:
    """The cron strings the Decide step actually matches on."""
    text = (workflow or WORKFLOW).read_text()
    step = text.split("- name: Decide")[1] if "- name: Decide" in text else ""
    found = re.search(r"fromJSON\('(\[[^)]*?\])'\)", step, re.S)
    return json.loads(found.group(1)) if found else []


def last_decide_trigger(session: dt.date,
                        workflow: Path | None = None) -> dt.datetime | None:
    """The latest scheduled firing that could still decide this session.

    None when the schedule offers none, which is a real answer and not a zero:
    the caller must not then invent a deadline.
    """
    close, open_at = overnight_window(session)
    cutoff = close + (open_at - close) * MAX_WINDOW_ELAPSED
    best = None
    for cron in decide_crons(workflow):
        minute, hour, _dom, _mon, dow = cron.split()
        for offset in (0, 1):
            day = session + dt.timedelta(days=offset)
            if not _dow_matches(dow, day):
                continue
            when = dt.datetime.combine(
                day, dt.time(int(hour), int(minute)), tzinfo=UTC)
            if close < when <= cutoff and (best is None or when > best):
                best = when
    return best


def decide_deadline(session: dt.date, fallback_hours: float,
                    margin_hours: float = 1.0,
                    workflow: Path | None = None) -> dt.datetime:
    """When a session with no decision has genuinely been missed.

    One hour past the last trigger that could still have decided it - enough for
    a run to start, read the news for a book of positions and append. Falls back
    to the flat grace when the schedule cannot be read, so a moved or unreadable
    workflow makes the gate no worse than it was.
    """
    try:
        last = last_decide_trigger(session, workflow)
    except (OSError, ValueError, IndexError, json.JSONDecodeError):
        last = None
    if last is None:
        return close_utc(session) + dt.timedelta(hours=fallback_hours)
    return last + dt.timedelta(hours=margin_hours)
