"""The calendar selector decides which nights get hedged, so its window has to be exact.

Nasdaq lists a report under the calendar date it is released. The overnight window
runs from one session's close to the next session's open, so only two of the four
date/time combinations fall inside it. The rule used to OR the two dates and ignore
the release time, which hedged the night before every after-hours report as well as
the night itself - two nights of cost per event, one protecting nothing.
"""
from __future__ import annotations

import datetime as dt
import unittest
from unittest import mock

from ballast import earnings

THU = dt.date(2026, 9, 10)          # next session is Friday 2026-09-11
FRI = dt.date(2026, 9, 11)


def calendar(**by_date):
    """Patch symbols_on with {date: {ticker: flag}}."""
    table = {dt.date.fromisoformat(d): v for d, v in by_date.items()}
    return mock.patch.object(earnings, "symbols_on", lambda day: table.get(day, {}))


class WindowMembershipCase(unittest.TestCase):
    def test_after_hours_on_the_session_is_inside(self):
        with calendar(**{"2026-09-10": {"ORCL": "time-after-hours"}}):
            self.assertEqual(earnings.scheduled_in_window("ORCL", THU), "time-after-hours")

    def test_pre_market_on_the_next_session_is_inside(self):
        with calendar(**{"2026-09-11": {"ORCL": "time-pre-market"}}):
            self.assertEqual(earnings.scheduled_in_window("ORCL", THU), "time-pre-market")

    def test_after_hours_on_the_next_session_is_outside(self):
        """The regression: the window shut at Friday's open, hours before this."""
        with calendar(**{"2026-09-11": {"ORCL": "time-after-hours"}}):
            self.assertIsNone(earnings.scheduled_in_window("ORCL", THU))

    def test_pre_market_on_the_session_is_outside(self):
        """It was released before this session even closed."""
        with calendar(**{"2026-09-10": {"ORCL": "time-pre-market"}}):
            self.assertIsNone(earnings.scheduled_in_window("ORCL", THU))

    def test_one_event_is_hedged_on_exactly_one_night(self):
        table = {"2026-09-10": {"ORCL": "time-after-hours"}}
        with calendar(**table):
            nights = [d for d in (dt.date(2026, 9, 9), THU, FRI)
                      if earnings.scheduled_in_window("ORCL", d)]
        self.assertEqual(nights, [THU])

    def test_a_missing_release_time_is_matched_on_date_alone(self):
        """Nasdaq only populates the flag for upcoming dates. Historical dates fall
        back to the date-only rule Gate 1 measured, so research and production agree."""
        with calendar(**{"2026-09-10": {"ORCL": "time-not-supplied"}}):
            self.assertEqual(earnings.scheduled_in_window("ORCL", THU), "time-not-supplied")
        with calendar(**{"2026-09-11": {"ORCL": "time-not-supplied"}}):
            self.assertEqual(earnings.scheduled_in_window("ORCL", THU), "time-not-supplied")

    def test_no_report_at_all(self):
        with calendar(**{"2026-09-10": {"AAPL": "time-after-hours"}}):
            self.assertIsNone(earnings.scheduled_in_window("ORCL", THU))


if __name__ == "__main__":
    unittest.main()
