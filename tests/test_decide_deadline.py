"""A session is only missing once its last chance to be decided has gone.

The coverage gate waited a flat four hours after the close. That matches the
schedule on a normal 21:00Z close, where the last decide trigger is 00:00Z, and
is two hours short on an early close. The half day after Thanksgiving closed at
18:00Z with its last trigger still at 00:00Z, so the gate failed the job at
22:51Z for a night that was decided shortly afterwards - crying before the
system had finished trying, which is how a gate teaches people to ignore it.
"""
from __future__ import annotations

import datetime as dt
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

# Imported after the path is extended above, which is what E402 is objecting to.
from ballast.report import DECIDE_GRACE_HOURS  # noqa: E402
from ballast.schedule import decide_crons, decide_deadline, last_decide_trigger  # noqa: E402
from ballast.sessions import close_utc, overnight_window  # noqa: E402

NORMAL = dt.date(2026, 11, 25)      # Wednesday, 21:00Z close
HALF_DAY = dt.date(2026, 11, 27)    # Friday after Thanksgiving, 18:00Z close


class TheDeadlineFollowsTheSchedule(unittest.TestCase):
    def test_the_two_fixtures_really_do_close_at_different_times(self):
        """Guards everything below: one close would prove nothing."""
        self.assertEqual(f"{close_utc(NORMAL):%H:%M}", "21:00")
        self.assertEqual(f"{close_utc(HALF_DAY):%H:%M}", "18:00")

    def test_an_early_close_gets_the_longer_wait(self):
        normal = decide_deadline(NORMAL, DECIDE_GRACE_HOURS) - close_utc(NORMAL)
        half = decide_deadline(HALF_DAY, DECIDE_GRACE_HOURS) - close_utc(HALF_DAY)
        self.assertGreater(half, normal,
                           "an earlier close leaves longer to the same 00:00Z "
                           "trigger, so the gate has to wait longer, not less")
        self.assertAlmostEqual(half.total_seconds() / 3600, 7.0, places=3)

    def test_a_normal_close_is_unchanged_by_the_new_derivation(self):
        """The flat four hours was right here; deriving it must not move it."""
        self.assertEqual(decide_deadline(NORMAL, DECIDE_GRACE_HOURS),
                         close_utc(NORMAL) + dt.timedelta(hours=DECIDE_GRACE_HOURS))

    def test_the_deadline_is_after_the_last_trigger_not_before(self):
        for session in (NORMAL, HALF_DAY):
            with self.subTest(session=session):
                last = last_decide_trigger(session)
                self.assertIsNotNone(last)
                self.assertGreater(decide_deadline(session, DECIDE_GRACE_HOURS),
                                   last)

    def test_no_trigger_is_offered_past_the_point_a_decision_is_refused(self):
        """night.run() refuses past half the window, so a later firing is no chance."""
        for session in (NORMAL, HALF_DAY):
            with self.subTest(session=session):
                close, open_at = overnight_window(session)
                self.assertLessEqual(last_decide_trigger(session),
                                     close + (open_at - close) * 0.5)

    def test_an_unreadable_schedule_falls_back_to_the_flat_grace(self):
        missing = ROOT / "no-such-workflow.yml"
        self.assertEqual(
            decide_deadline(HALF_DAY, DECIDE_GRACE_HOURS, workflow=missing),
            close_utc(HALF_DAY) + dt.timedelta(hours=DECIDE_GRACE_HOURS))

    def test_it_reads_the_decide_crons_and_not_the_settle_ones(self):
        crons = decide_crons()
        self.assertIn("0 0 * * 2-6", crons)
        self.assertNotIn("30 14 * * 1-5", crons, "that is a settle trigger")


class TheGateDoesNotCryEarly(unittest.TestCase):
    """Replays 2026-11-27, the run that mailed the failure.

    The ledger here deliberately STOPS before the half day. Against the real
    chain, where 11-27 was decided soon after, these would pass whatever the
    grace was - the gate would be quiet for the wrong reason and the test would
    be checking nothing.
    """

    def setUp(self):
        import json
        import tempfile
        from unittest import mock

        from ballast import config
        self.tmp = tempfile.TemporaryDirectory()
        path = Path(self.tmp.name) / "ledger.jsonl"
        with path.open("w") as fh:
            for day in ("2026-11-20", "2026-11-23", "2026-11-24", "2026-11-25"):
                fh.write(json.dumps({"kind": "night_summary",
                                     "body": {"session": day}}) + "\n")
        self.patch = mock.patch.object(config, "LEDGER_PATH", path)
        self.patch.start()
        self.addCleanup(self.patch.stop)
        self.addCleanup(self.tmp.cleanup)
        from check_coverage import missing
        self.missing = missing

    def test_the_fixture_really_does_leave_the_half_day_undecided(self):
        """Without this the two tests below could pass by accident."""
        long_after = dt.datetime(2026, 12, 1, tzinfo=dt.timezone.utc)
        self.assertIn(HALF_DAY, self.missing(10, now=long_after))

    def test_it_stays_quiet_while_a_chance_remains(self):
        at = dt.datetime(2026, 11, 27, 22, 51, tzinfo=dt.timezone.utc)
        self.assertNotIn(HALF_DAY, self.missing(10, now=at),
                         "the 00:00Z trigger had not fired yet, so the night "
                         "was not missing - it was still being worked on")

    def test_it_still_speaks_once_every_chance_is_gone(self):
        """Waiting longer must not mean never."""
        at = dt.datetime(2026, 11, 28, 2, 0, tzinfo=dt.timezone.utc)
        self.assertIn(HALF_DAY, self.missing(10, now=at))


if __name__ == "__main__":
    unittest.main()
