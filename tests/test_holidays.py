"""The exchange calendar.

Holidays were previously ignored, so a window spanning one was mislabelled as an
ordinary overnight - a Thursday-to-Monday Easter window reported as 17.5 hours
rather than 89.5. That understates exposure on exactly the longest windows.

Rules are computed rather than tabulated, so these tests pin the rules against
known-correct NYSE dates rather than restating a table.
"""
from __future__ import annotations

import datetime as dt
import unittest
import unittest.mock

from ballast.holidays import (closes_early, early_closes, easter, holidays,
                              is_trading_day)
from ballast.sessions import next_session, window_hours


class TestHolidayRules(unittest.TestCase):
    def test_easter_matches_known_dates(self):
        for year, day in [(2024, (3, 31)), (2025, (4, 20)), (2026, (4, 5)),
                          (2027, (3, 28))]:
            self.assertEqual(easter(year), dt.date(year, *day), year)

    def test_2026_matches_the_published_nyse_calendar(self):
        expected = {
            dt.date(2026, 1, 1),    # New Year's Day
            dt.date(2026, 1, 19),   # MLK
            dt.date(2026, 2, 16),   # Washington's Birthday
            dt.date(2026, 4, 3),    # Good Friday
            dt.date(2026, 5, 25),   # Memorial Day
            dt.date(2026, 6, 19),   # Juneteenth
            dt.date(2026, 7, 3),    # Independence Day observed (4th is a Saturday)
            dt.date(2026, 9, 7),    # Labor Day
            dt.date(2026, 11, 26),  # Thanksgiving
            dt.date(2026, 12, 25),  # Christmas
        }
        self.assertEqual(holidays(2026), expected)

    def test_a_saturday_holiday_is_observed_on_the_friday(self):
        self.assertIn(dt.date(2026, 7, 3), holidays(2026))   # July 4 is a Saturday
        self.assertNotIn(dt.date(2026, 7, 4), holidays(2026))

    def test_a_sunday_holiday_is_observed_on_the_monday(self):
        self.assertIn(dt.date(2027, 12, 24), holidays(2027))  # Christmas is a Saturday
        self.assertIn(dt.date(2027, 7, 5), holidays(2027))    # July 4 is a Sunday

    def test_a_saturday_new_year_is_not_observed(self):
        """The exchange does not close the preceding 31 December."""
        self.assertNotIn(dt.date(2021, 12, 31), holidays(2022))

    def test_juneteenth_only_from_2022(self):
        self.assertNotIn(dt.date(2021, 6, 18), holidays(2021))
        self.assertIn(dt.date(2022, 6, 20), holidays(2022))   # 19th is a Sunday

    def test_early_closes(self):
        self.assertEqual(early_closes(2026),
                         {dt.date(2026, 11, 27), dt.date(2026, 12, 24)})
        self.assertTrue(closes_early(dt.date(2026, 11, 27)))
        self.assertFalse(closes_early(dt.date(2026, 11, 30)))

    def test_an_early_close_is_not_also_a_holiday(self):
        for year in range(2024, 2030):
            self.assertFalse(early_closes(year) & holidays(year), year)


class TestSessionsRespectHolidays(unittest.TestCase):
    def test_holidays_are_not_trading_days(self):
        self.assertFalse(is_trading_day(dt.date(2026, 12, 25)))
        self.assertFalse(is_trading_day(dt.date(2026, 9, 12)))   # Saturday
        self.assertTrue(is_trading_day(dt.date(2026, 9, 11)))

    def test_next_session_skips_a_holiday(self):
        self.assertEqual(next_session(dt.date(2026, 11, 25)), dt.date(2026, 11, 27))
        self.assertEqual(next_session(dt.date(2026, 4, 2)), dt.date(2026, 4, 6))

    def test_a_holiday_window_is_measured_at_its_real_length(self):
        """Easter: Thursday close to Monday open, not a 17.5 hour overnight."""
        self.assertAlmostEqual(window_hours(dt.date(2026, 4, 2)), 89.5)
        self.assertAlmostEqual(window_hours(dt.date(2026, 9, 8)), 17.5)

    def test_an_early_close_lengthens_the_window(self):
        self.assertGreater(window_hours(dt.date(2026, 12, 24)),
                           window_hours(dt.date(2026, 12, 23)))

    def test_the_search_for_a_trading_day_is_bounded(self):
        """Patch where the name is used, not where it is defined - `sessions`
        imported it directly, so patching `holidays` would have no effect."""
        from ballast import sessions
        with unittest.mock.patch.object(sessions, "is_trading_day", return_value=False):
            with self.assertRaises(RuntimeError):
                next_session(dt.date(2026, 9, 8))


if __name__ == "__main__":
    unittest.main()
