"""Every scheduled trigger must reach the step it was added for.

This file exists because of 2026-10-02. GitHub dropped the 21:00Z decide cron and
its 22:30Z backup; the only job that fired was the 17:00Z SETTLE cron arriving
4h10m late. A delayed schedule is delivered under its ORIGINAL cron string, so
`github.event.schedule` read "0 17 * * 1-5", which matched the settle branch and
skipped deciding. The job went green having decided nothing, and the
Friday-to-Monday window - 65.5 hours, the longest exposure this book carries -
had no decision on the chain until it was run by hand.

Nothing in the repository could have caught that: the cron list and the step
conditions that read it were two hand-maintained copies of the same fact. These
tests make them one.
"""
from __future__ import annotations

import datetime as dt
import json
import re
import unittest
from pathlib import Path

import yaml

from ballast.sessions import close_utc, current_session

WORKFLOW = Path(__file__).resolve().parents[1] / ".github/workflows/nightly.yml"

# Minutes after the close by which the night should be decided. The first thirteen
# hedges went on a median 21% of the way through the window and were graded as
# though they had been on throughout; the re-grade turned the book's drawdown from
# better than unhedged to worse. The fix is a trigger that fires near the bell.
DECIDE_BY_MINUTES = 15


def workflow() -> dict:
    return yaml.safe_load(WORKFLOW.read_text())


def crons() -> list[str]:
    return [c["cron"] for c in workflow()[True]["schedule"]]


def step(name: str) -> dict:
    for s in workflow()["jobs"]["run"]["steps"]:
        if s.get("name", "").startswith(name):
            return s
    raise AssertionError(f"no step named {name!r}")


def wired(name: str) -> set[str]:
    """The cron strings a step's `if` actually matches on."""
    found = re.search(r"fromJSON\('(\[[^)]*?\])'\)", step(name)["if"], re.S)
    return set(json.loads(found.group(1))) if found else set()


def minute_of(cron: str) -> tuple[int, int]:
    minute, hour = cron.split()[0], cron.split()[1]
    return int(hour), int(minute)


class EveryCronReachesItsStep(unittest.TestCase):
    def test_no_cron_fires_into_nothing(self):
        """The failure that cost a night: a trigger matching no branch."""
        handled = wired("Decide") | wired("Settle") | wired("Re-grade")
        orphans = [c for c in crons() if c not in handled]
        self.assertEqual(orphans, [],
                         "these crons fire and no step claims them, so the job "
                         "runs, goes green, and does nothing")

    def test_decide_and_settle_never_claim_the_same_cron(self):
        both = wired("Decide") & wired("Settle")
        self.assertEqual(both, set(),
                         "one trigger cannot mean both halves - a delayed "
                         "schedule arrives under its original string")

    def test_every_wired_cron_is_actually_scheduled(self):
        """The other direction: a condition naming a cron that no longer fires."""
        for name in ("Decide", "Settle"):
            for c in wired(name):
                self.assertIn(c, crons(),
                              f"{name} waits on {c!r}, which is not scheduled")


class TheNightIsDecidedNearTheClose(unittest.TestCase):
    def test_a_trigger_fires_within_minutes_of_the_bell(self):
        session = dt.date(2026, 10, 1)
        close = close_utc(session)
        earliest = min(
            (dt.datetime.combine(session, dt.time(h, m), tzinfo=dt.timezone.utc)
             for h, m in (minute_of(c) for c in wired("Decide"))),
            key=lambda when: abs((when - close).total_seconds()))
        late = (earliest - close).total_seconds() / 60
        self.assertGreater(late, 0,
                           "a decide trigger before the close resolves to the "
                           "PREVIOUS session and would decide the wrong night")
        self.assertLessEqual(late, DECIDE_BY_MINUTES,
                             f"earliest decide trigger is {late:.0f} min after "
                             f"the close; the hedge has to be on before the "
                             f"after-hours release, not after it")

    def test_firing_before_the_close_would_pick_the_wrong_session(self):
        """Why the trigger is at :05 and not on the hour or earlier."""
        close = close_utc(dt.date(2026, 10, 1))
        self.assertEqual(current_session(close - dt.timedelta(minutes=5)),
                         dt.date(2026, 9, 30))
        self.assertEqual(current_session(close + dt.timedelta(minutes=5)),
                         dt.date(2026, 10, 1))

    def test_the_backups_are_still_there(self):
        """The early trigger replaces nothing - GitHub drops schedules."""
        self.assertGreaterEqual(len(wired("Decide")), 3,
                                "one trigger is one chance, and GitHub dropped "
                                "two in a row on 2026-10-02")


if __name__ == "__main__":
    unittest.main()
