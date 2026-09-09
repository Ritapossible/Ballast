"""Session calendar correctness.

An hour of drift here silently corrupts every downstream number, so the DST
transitions inside our data sample are pinned by test.
"""
from __future__ import annotations

import datetime as dt
import unittest

from ballast.sessions import close_utc, next_session, open_utc, window_hours


class TestDaylightSaving(unittest.TestCase):
    def test_edt_close_is_2000_utc(self):
        self.assertEqual(close_utc(dt.date(2026, 6, 15)).hour, 20)

    def test_est_close_is_2100_utc(self):
        self.assertEqual(close_utc(dt.date(2026, 1, 15)).hour, 21)

    def test_both_transitions_inside_the_sample(self):
        # 2025-11-02 EDT->EST
        self.assertEqual(close_utc(dt.date(2025, 10, 31)).hour, 20)
        self.assertEqual(close_utc(dt.date(2025, 11, 3)).hour, 21)
        # 2026-03-08 EST->EDT
        self.assertEqual(close_utc(dt.date(2026, 3, 6)).hour, 21)
        self.assertEqual(close_utc(dt.date(2026, 3, 9)).hour, 20)

    def test_open_is_0930_et_in_both_regimes(self):
        self.assertEqual((open_utc(dt.date(2026, 6, 15)).hour,
                          open_utc(dt.date(2026, 6, 15)).minute), (13, 30))
        self.assertEqual((open_utc(dt.date(2026, 1, 15)).hour,
                          open_utc(dt.date(2026, 1, 15)).minute), (14, 30))


class TestWindows(unittest.TestCase):
    def test_weeknight_is_17_5_hours(self):
        self.assertAlmostEqual(window_hours(dt.date(2026, 9, 8)), 17.5)   # Tuesday

    def test_friday_spans_the_weekend(self):
        friday = dt.date(2026, 9, 11)
        self.assertEqual(friday.weekday(), 4)
        self.assertEqual(next_session(friday), dt.date(2026, 9, 14))
        self.assertAlmostEqual(window_hours(friday), 65.5)

    def test_weekend_window_is_the_longest_exposure(self):
        self.assertGreater(window_hours(dt.date(2026, 9, 11)),
                           3 * window_hours(dt.date(2026, 9, 8)))


if __name__ == "__main__":
    unittest.main()
