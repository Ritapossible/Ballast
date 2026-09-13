"""Paper-trading metrics: the half of this track that is scored arithmetically.

The replay computed Sharpe, max drawdown and win rate over history. The live log
computed none of them, so the quantitative half of the score had nothing to read.
"""
from __future__ import annotations

import unittest

from ballast.metrics import _max_drawdown, _sharpe, book_series, paper_metrics


def row(session, action, realised, unhedged):
    return {"session": session, "action": action, "ticker": "X",
            "realised_bp": realised, "unhedged_bp": unhedged,
            "counterfactual_bp": unhedged - realised, "value_added_bp": 0.0}


class DrawdownCase(unittest.TestCase):
    def test_a_curve_that_only_rises_has_no_drawdown(self):
        self.assertEqual(_max_drawdown([10.0, 20.0, 5.0]), 0.0)

    def test_it_measures_peak_to_trough_not_first_to_last(self):
        # +100 then -300 then +150: trough is 200 below the peak, ends only 50 down.
        self.assertEqual(_max_drawdown([100.0, -300.0, 150.0]), -300.0)

    def test_a_later_deeper_trough_wins(self):
        self.assertEqual(_max_drawdown([-10.0, 30.0, -50.0, -40.0]), -90.0)

    def test_empty(self):
        self.assertEqual(_max_drawdown([]), 0.0)


class SharpeCase(unittest.TestCase):
    def test_one_night_is_not_a_sharpe(self):
        import math
        self.assertTrue(math.isnan(_sharpe([12.0])))

    def test_a_flat_series_has_no_dispersion_to_divide_by(self):
        import math
        self.assertTrue(math.isnan(_sharpe([5.0, 5.0, 5.0])))

    def test_it_is_annualised(self):
        import math
        r = [1.0, -1.0, 2.0, -2.0, 3.0]
        import statistics as st
        expected = (st.mean(r) / st.stdev(r)) * math.sqrt(252)
        self.assertAlmostEqual(_sharpe(r), expected, places=9)


class BookSeriesCase(unittest.TestCase):
    def test_one_point_per_session_equal_weighted(self):
        rows = [row("2026-09-10", "HEDGE", -10.0, -400.0),
                row("2026-09-10", "NO_HEDGE", 30.0, 30.0),
                row("2026-09-11", "NO_HEDGE", -20.0, -20.0)]
        self.assertEqual(book_series(rows),
                         [("2026-09-10", 10.0, -185.0), ("2026-09-11", -20.0, -20.0)])

    def test_sessions_come_out_in_order(self):
        rows = [row("2026-09-11", "NO_HEDGE", 1.0, 1.0),
                row("2026-09-09", "NO_HEDGE", 2.0, 2.0)]
        self.assertEqual([s for s, _, _ in book_series(rows)],
                         ["2026-09-09", "2026-09-11"])


class PaperMetricsCase(unittest.TestCase):
    def test_the_hedge_shows_up_as_a_smaller_drawdown(self):
        """The product's whole claim, stated as the metric the track scores."""
        rows = [row("2026-09-09", "HEDGE", -12.0, -500.0),
                row("2026-09-10", "NO_HEDGE", -40.0, -40.0)]
        m = paper_metrics(rows)
        self.assertGreater(m["hedged_max_dd_bp"], m["unhedged_max_dd_bp"])

    def test_win_rate_counts_hedges_that_cut_the_move(self):
        rows = [row("2026-09-09", "HEDGE", -12.0, -500.0),     # cut
                row("2026-09-10", "HEDGE", -80.0, -30.0),      # did not
                row("2026-09-11", "NO_HEDGE", 5.0, 5.0)]       # not a hedge
        m = paper_metrics(rows)
        self.assertEqual((m["hedges"], m["hedges_that_cut"], m["win_rate_pct"]), (2, 1, 50))

    def test_no_hedges_means_no_win_rate_rather_than_zero(self):
        m = paper_metrics([row("2026-09-09", "NO_HEDGE", 5.0, 5.0)])
        self.assertIsNone(m["win_rate_pct"])
        self.assertEqual(m["orders"], 0)

    def test_an_empty_log_does_not_explode(self):
        m = paper_metrics([])
        self.assertEqual(m["nights"], 0)
        self.assertIsNone(m["hedged_sharpe"])


if __name__ == "__main__":
    unittest.main()
