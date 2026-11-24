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
from typing import ClassVar

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
    # One in EDT and one in EST. A cron is a fixed UTC time and the US close is
    # not: 20:00Z in summer, 21:00Z in winter. Testing one date only is how a
    # near-close trigger that was correct on 2026-10-03 silently became a trigger
    # firing 55 minutes BEFORE the close on 2026-11-01, deciding the previous
    # session and contributing nothing for three weeks.
    SESSIONS: ClassVar[tuple] = (dt.date(2026, 10, 1), dt.date(2026, 11, 23))

    def test_a_trigger_fires_soon_after_the_bell_in_both_dst_regimes(self):
        for session in self.SESSIONS:
            with self.subTest(session=session, close=f"{close_utc(session):%H:%MZ}"):
                close = close_utc(session)
                after = [
                    (dt.datetime.combine(session, dt.time(h, m),
                                         tzinfo=dt.timezone.utc) - close).total_seconds() / 60
                    for h, m in (minute_of(c) for c in wired("Decide"))]
                # Only triggers AFTER the bell count; one before it resolves to
                # the previous session, so it is not cover for this night at all.
                usable = [m for m in after if m > 0]
                self.assertTrue(usable, "no decide trigger fires after this close")
                self.assertLessEqual(
                    min(usable), DECIDE_BY_MINUTES,
                    f"earliest decide trigger after the {close:%H:%MZ} close is "
                    f"{min(usable):.0f} min late; the hedge has to be on before "
                    f"the after-hours release, not after it")

    def test_the_close_really_does_move_between_the_two_sessions(self):
        """Guards the test above: two dates in the same regime would prove nothing."""
        closes = {f"{close_utc(s):%H:%MZ}" for s in self.SESSIONS}
        self.assertEqual(len(closes), 2, f"both sessions share a close: {closes}")

    def test_firing_before_the_close_would_pick_the_wrong_session(self):
        """Why the trigger is at :05 and not on the hour or earlier."""
        for session in self.SESSIONS:
            with self.subTest(session=session):
                close = close_utc(session)
                self.assertNotEqual(
                    current_session(close - dt.timedelta(minutes=5)), session,
                    "a run before the bell must not resolve to this session")
                self.assertEqual(
                    current_session(close + dt.timedelta(minutes=5)), session)

    def test_the_backups_are_still_there(self):
        """The early trigger replaces nothing - GitHub drops schedules."""
        self.assertGreaterEqual(len(wired("Decide")), 3,
                                "one trigger is one chance, and GitHub dropped "
                                "two in a row on 2026-10-02")


if __name__ == "__main__":
    unittest.main()
