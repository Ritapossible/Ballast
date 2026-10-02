"""A hedge is credited only with the part of the night it was actually on.

Settlement graded every hedge close-to-open, as though the perp short had been on
from the closing bell. It never was: the 21:00Z cron is routinely delayed and the
00:00Z backup fires instead, so hedges went on hours into the window. Grading the
whole night subtracts the perp leg from a fall the hedge missed, and on NKE
2026-10-01 that recorded +17 bp on a night that cost 526 bp.

Each test below stands for a way that correction could come undone: a split that
does not add back to the night it halves, a grader that quietly reverts to the
full window, a correction that edits the signed record instead of sitting beside
it, one that reruns and double-counts, or a page that shows the corrected number
while hiding which number it replaced.
"""
from __future__ import annotations

import datetime as dt
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from ballast import config, regrade, report
from ballast.costs import HEDGE_COST_BP
from ballast.ledger import Ledger
from ballast.morning import _settle_one
from ballast.overnight import overnight_returns, split_returns
from ballast.sessions import overnight_window

SESSION = dt.date(2026, 10, 1)
HOUR_MS = 3_600_000


def bars_from(path: dict[dt.datetime, float]) -> dict[int, tuple[float, float]]:
    """Flat hourly bars at a given price, so open == close and the hour is the price.

    Both legs of the split price off the SAME mid bar, so a flat bar makes the
    arithmetic checkable by hand without making the identity trivial - the three
    lookups still land on three different hours.
    """
    return {int(when.timestamp() * 1000): (price, price) for when, price in path.items()}


def hourly(start: dt.datetime, prices: list[float]) -> dict[int, tuple[float, float]]:
    return bars_from({start + dt.timedelta(hours=i): p for i, p in enumerate(prices)})


class TheSplit(unittest.TestCase):
    """split_returns halves one night. The halves must be the same night."""

    def setUp(self):
        self.close, self.open = overnight_window(SESSION)
        # A fall then a partial rebound - the earnings shape the late hedge misses.
        hours = int((self.open - self.close).total_seconds() // 3600) + 2
        self.prices = [100.0] + [90.0] * (hours - 1)
        self.prices[-1] = 95.0
        self.bars = hourly(self.close, self.prices)

    def test_the_halves_add_back_to_the_whole_night(self):
        full = overnight_returns(self.bars)[SESSION]
        for hours in range(0, int((self.open - self.close).total_seconds() // 3600)):
            at = self.close + dt.timedelta(hours=hours)
            pre, post = split_returns(self.bars, SESSION, at)
            self.assertAlmostEqual(pre + post, full, places=12,
                                   msg=f"split at +{hours}h is a second definition "
                                       f"of the night, not a cut through it")

    def test_a_cut_outside_the_window_is_refused(self):
        for at in (self.close - dt.timedelta(hours=1),
                   self.open + dt.timedelta(hours=1)):
            self.assertIsNone(split_returns(self.bars, SESSION, at))

    def test_a_missing_bar_is_refused_rather_than_interpolated(self):
        gap = dict(self.bars)
        at = self.close + dt.timedelta(hours=4)
        del gap[int(at.timestamp() * 1000)]
        self.assertIsNone(split_returns(gap, SESSION, at),
                          "a night priced through a hole in the candles is a guess")


class TheGrade(unittest.TestCase):
    """The hedge carries the post-hedge move only. The holder eats the rest."""

    def setUp(self):
        self.close, _ = overnight_window(SESSION)
        self.record = {"ticker": "NKE", "action": "HEDGE",
                       "spot_symbol": "RNKEUSDT", "perp_symbol": "NKEUSDT"}

    def grade(self, split):
        spot = split[0] + split[1]
        perp = split[2] + split[3]
        return _settle_one(self.record, spot, perp, HEDGE_COST_BP, split)

    def test_a_fall_before_the_hedge_is_not_credited_to_the_hedge(self):
        # The whole move is a 500 bp fall BEFORE the hedge; the perp tracks it.
        # Full-window arithmetic would cancel the two and record roughly -cost.
        split = (-0.05, 0.0, -0.05, 0.0)
        row = self.grade(split)
        self.assertAlmostEqual(row["realised_bp"], round(-500 - HEDGE_COST_BP, 1), places=6)
        self.assertEqual(row["unhedged_bp"], -500.0)
        self.assertFalse(row["cut_the_move"],
                         "a hedge placed after the fall cannot have cut it")

    def test_the_hedge_is_credited_with_the_fall_it_was_on_for(self):
        split = (0.0, -0.05, 0.0, -0.05)
        row = self.grade(split)
        self.assertAlmostEqual(row["realised_bp"], round(-HEDGE_COST_BP, 1), places=6)
        self.assertTrue(row["cut_the_move"])

    def test_value_added_is_the_short_leg_the_hedge_actually_held(self):
        # The only thing a hedge changes is the perp return after it went on.
        split = (-0.02, 0.03, -0.01, 0.04)
        row = self.grade(split)
        self.assertAlmostEqual(row["value_added_bp"],
                               round(-split[3] * 1e4 - HEDGE_COST_BP, 1), places=6)

    def test_without_a_split_the_old_full_window_grade_is_used(self):
        # Not a blessing of the old arithmetic: a row that cannot be split has to
        # keep the grade its signed settlement carries, or the page would show a
        # corrected figure for a night nothing re-priced.
        row = _settle_one(self.record, -0.05, -0.05, HEDGE_COST_BP, None)
        self.assertAlmostEqual(row["realised_bp"], round(-HEDGE_COST_BP, 1), places=6)
        self.assertIsNone(row["pre_hedge_bp"])


class Case(unittest.TestCase):
    """A throwaway ledger and stubbed candles, so nothing touches the network."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.ledger_path = self.root / "ledger.jsonl"
        self.patches = [
            mock.patch.object(config, "LEDGER_PATH", self.ledger_path),
            mock.patch.object(config, "STATE", self.root),
            mock.patch.object(config, "secret", return_value=b"t"),
            mock.patch.object(regrade, "market_bars", self._bars),
        ]
        for p in self.patches:
            p.start()
        self.close, self.open = overnight_window(SESSION)
        hours = int((self.open - self.close).total_seconds() // 3600) + 2
        # Spot falls 10% in the first hour and holds; the perp does the same. A
        # hedge four hours in therefore protects nothing and costs the fee.
        self.spot = hourly(self.close, [100.0] + [90.0] * (hours - 1))
        self.perp = hourly(self.close, [100.0] + [90.0] * (hours - 1))
        self.at = self.close + dt.timedelta(hours=4)

    def tearDown(self):
        for p in reversed(self.patches):
            p.stop()
        self.tmp.cleanup()

    def _bars(self, symbol, kind="spot", **kw):
        return self.perp if kind == "mix" else self.spot

    def decision(self):
        return {"ticker": "NKE", "session": SESSION.isoformat(), "action": "HEDGE",
                "spot_symbol": "RNKEUSDT", "perp_symbol": "NKEUSDT",
                "sigma_bp": 74.7, "rationale": "earnings",
                "inputs": {"decided_by": "model"},
                "fill": {"at": self.at.isoformat(), "venue": "simulated",
                         "side": "sell", "paper": True}}

    def seed(self):
        lg = Ledger(self.ledger_path, b"t")
        lg.append("decision", self.decision())
        # A refusal beside the hedge, because a real session is mostly refusals -
        # and because a count that walks every row instead of only the hedges has
        # to come out wrong somewhere for a test to catch it.
        lg.append("decision", {"ticker": "AAPL", "session": SESSION.isoformat(),
                               "action": "NO_HEDGE", "spot_symbol": "RAAPLUSDT",
                               "perp_symbol": "AAPLUSDT", "sigma_bp": 40.0,
                               "rationale": "nothing scheduled",
                               "inputs": {"decided_by": "model"}})
        # The settlement as it was actually written: full-window, hedge looks free.
        lg.append("settlement", {
            "session": SESSION.isoformat(), "decisions": 2, "hedged": 1,
            "hedges_that_cut": 1,
            "rows": [{"ticker": "NKE", "action": "HEDGE", "unhedged_bp": -1053.6,
                      "realised_bp": -11.3, "counterfactual_bp": -1053.6,
                      "value_added_bp": 1042.3, "cut_the_move": True,
                      "cost_bp": 11.3},
                     {"ticker": "AAPL", "action": "NO_HEDGE", "unhedged_bp": 120.0,
                      "realised_bp": 120.0, "counterfactual_bp": 108.7,
                      "value_added_bp": 11.3, "cut_the_move": None,
                      "cost_bp": 11.3}]})
        return lg


class TheCorrection(Case):
    def test_it_grades_the_settled_hedge_from_its_fill(self):
        self.seed()
        result = regrade.run()
        self.assertEqual(result["regraded"], 1)
        row = result["rows"][0]
        self.assertAlmostEqual(row["pre_hedge_bp"], -1053.6, places=1)
        self.assertAlmostEqual(row["post_hedge_bp"], 0.0, places=6)
        self.assertFalse(row["cut_the_move"])
        self.assertEqual(row["hedge_at"], self.at.isoformat())

    def test_the_signed_settlement_is_left_exactly_as_written(self):
        lg = self.seed()
        before = self.ledger_path.read_text()
        regrade.run()
        self.assertTrue(self.ledger_path.read_text().startswith(before),
                        "the correction rewrote history instead of appending to it")
        lg.verify()
        self.assertEqual(lg.records("settlement")[0]["body"]["rows"][0]["realised_bp"],
                         -11.3)

    def test_the_correction_names_what_it_supersedes(self):
        self.seed()
        regrade.run()
        body = Ledger(self.ledger_path, b"t").records("regrade")[0]["body"]
        self.assertEqual(body["supersedes"], "settlement")
        self.assertIn("fill timestamp", body["reason"])

    def test_rerunning_adds_nothing(self):
        self.seed()
        regrade.run()
        after = self.ledger_path.read_text()
        second = regrade.run()
        self.assertEqual(second["regraded"], 0)
        self.assertEqual(self.ledger_path.read_text(), after,
                         "a second pass double-counts the same night")

    def test_an_unsettled_session_is_left_alone(self):
        lg = Ledger(self.ledger_path, b"t")
        lg.append("decision", self.decision())      # decided, never settled
        self.assertEqual(regrade.run()["regraded"], 0)


class ThePage(Case):
    def test_the_table_shows_the_corrected_grade(self):
        self.seed()
        regrade.run()
        snap = report.Site()
        row = next(r for r in snap.rows if r["ticker"] == "NKE")
        self.assertAlmostEqual(row["realised_bp"], -1064.9, places=1)
        self.assertFalse(row["cut_the_move"])

    def test_the_superseded_grade_stays_on_the_row(self):
        self.seed()
        regrade.run()
        snap = report.Site()
        row = next(r for r in snap.rows if r["ticker"] == "NKE")
        self.assertEqual(row["superseded"]["realised_bp"], -11.3)
        self.assertTrue(row["superseded"]["cut_the_move"],
                        "the page cannot say what it corrected if it drops it")
        self.assertEqual(len(snap.regraded), 1)

    def test_an_uncorrected_row_carries_no_correction(self):
        self.seed()
        snap = report.Site()
        row = next(r for r in snap.rows if r["ticker"] == "NKE")
        self.assertNotIn("superseded", row)
        self.assertEqual(snap.regraded, [])


if __name__ == "__main__":
    unittest.main()


class TheDisclosure(Case):
    """The page cannot show a corrected number without saying what it corrected."""

    def setUp(self):
        super().setUp()
        self.seed()
        regrade.run()
        self.site = report.Site()

    def test_the_note_says_the_grade_moved_and_why(self):
        note = self.site.tile_scope
        self.assertIn("re-graded", note)
        self.assertIn("00:00Z backup", note)
        self.assertIn("4.0 hours after the close", note)

    def test_the_note_names_the_largest_correction_from_the_rows(self):
        note = self.site.tile_scope
        # Settled -11 bp, re-graded -1,065 bp: a 1,054 bp swing, all computed.
        self.assertIn("NKE on 2026-10-01", note)
        self.assertIn("-11 bp as settled", note)
        self.assertIn("-1,065 bp as re-graded", note)
        self.assertIn("1,054 bp swing", note)

    def test_a_flipped_verdict_is_counted_in_the_note(self):
        self.assertIn("One verdict flipped", self.site.tile_scope)

    def test_the_row_carries_the_grade_it_replaced(self):
        page = self.site.settled_page()
        self.assertIn("re-graded from the fill", page)
        self.assertIn("settled as -11 bp", page)

    def test_the_corrected_verdict_reaches_the_table(self):
        page = self.site.settled_page()
        self.assertIn('data-label="Verdict">did not cut', page)
        self.assertNotIn('data-label="Verdict">cut the move', page)
        self.assertIn('<div class="n">0/1</div>', page)   # the tile counts it too


class TheInsuranceClaim(unittest.TestCase):
    """The page's verdict on its own drawdown must be read off the drawdown.

    "It should show up as a smaller worst case, and it does" was typed beside the
    two numbers that decide it. Re-grading the hedges from their fill timestamps
    pushed the hedged drawdown PAST the untouched one, and the sentence carried on
    asserting the opposite of the figures printed immediately after it.
    """

    def block(self, hedged_dd, unhedged_dd, hedged_total, unhedged_total):
        site = report.Site.__new__(report.Site)
        metrics = {"nights": 17, "positions": 204, "hedges": 11,
                   "hedges_that_cut": 10, "hedges_ungraded": 2, "orders": 11,
                   "sessions": 17, "win_rate_pct": 91, "fees_bp_per_hedge": 11.3,
                   "hedged_max_dd_bp": hedged_dd, "unhedged_max_dd_bp": unhedged_dd,
                   "hedged_total_bp": hedged_total, "unhedged_total_bp": unhedged_total,
                   "hedged_sharpe": 2.0, "unhedged_sharpe": 2.53}
        with mock.patch.object(report, "paper_metrics", return_value=metrics), \
             mock.patch.object(report.Site, "rows", [], create=True), \
             mock.patch.object(report.Site, "clean", [], create=True):
            return site.paper_metrics_block

    def test_a_worse_drawdown_is_not_reported_as_protection(self):
        block = self.block(-235.2, -227.0, 208.7, 279.3)
        self.assertIn("On this record it does not, and that is the result", block)
        self.assertNotIn("and it does:", block)

    def test_a_better_drawdown_is_still_reported_as_protection(self):
        block = self.block(-202.9, -227.0, 296.8, 279.3)
        self.assertIn("On this record it does:", block)
        self.assertNotIn("it does not", block)

    def test_the_return_sentence_follows_the_returns(self):
        self.assertIn("returned less than", self.block(-235.2, -227.0, 208.7, 279.3))
        self.assertIn("returned more than", self.block(-235.2, -227.0, 300.0, 279.3))


class TheTape(Case):
    """The tape on the landing page must not quote the verdict the page retracted.

    The settlement summary carries its own `hedges_that_cut`, written when the
    night was graded over the whole close-to-open window, and the re-grade does
    not touch that signed body. Reading it there printed "1 hedged, 1 cut the
    move" on the first element of the site for the one night the settled page had
    already corrected to "did not cut".
    """

    def setUp(self):
        super().setUp()
        self.seed()
        regrade.run()
        self.site = report.Site()

    def test_the_tape_reports_the_corrected_verdict(self):
        tape = self.site._settled_tape()
        self.assertIn("1 hedged, 0 cut the move", tape)
        self.assertNotIn("1 cut the move", tape)

    def test_the_tape_agrees_with_the_settled_table(self):
        # Same derivation, so the two surfaces cannot disagree about one night.
        hedged, cut = self.site._graded(SESSION.isoformat())
        self.assertEqual((hedged, cut), (1, 0))
        self.assertIn('data-label="Verdict">did not cut', self.site.settled_page())

    def test_the_summary_still_carries_its_original_count(self):
        # The point of a correction beside the record: the old count is not erased.
        summary = Ledger(self.ledger_path, b"t").records("settlement")[0]["body"]
        self.assertEqual(summary["hedges_that_cut"], 1)
