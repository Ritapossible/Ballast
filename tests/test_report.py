"""The public pages must build from any ledger state, including an empty one.

A demo that errors on the day is worth less than no demo, and the handbook makes an
accessible demo a required material.
"""
from __future__ import annotations

import datetime as dt
import os
import re
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from ballast import config, docs_page, report
from ballast.ledger import Ledger


def build_site(entries) -> dict[str, str]:
    """Render every page against a throwaway ledger."""
    with tempfile.TemporaryDirectory() as d:
        ledger_path = Path(d) / "ledger.jsonl"
        lg = Ledger(ledger_path, b"t")
        for kind, body in entries:
            lg.append(kind, body)
        with mock.patch.object(config, "LEDGER_PATH", ledger_path), \
             mock.patch.object(config, "secret", return_value=b"t"), \
             mock.patch.object(report, "OUT_DIR", Path(d)), \
             mock.patch.object(docs_page, "OUT", Path(d) / "docs.html"):
            pages = {p.name: p.read_text() for p in report.build()}
            pages["docs.html"] = docs_page.build().read_text()
            return pages


POPULATED = [
    ("decision", {"ticker": "ORCL", "session": "2026-09-10", "action": "HEDGE",
                  "sigma_bp": 240.0, "notional_usdt": 1000.0,
                  "rationale": "event reader judged HEDGE",
                  "inputs": {"decided_by": "model"}}),
    ("night_summary", {"session": "2026-09-10", "positions": 1, "hedged": 1,
                       "window_hours": 17.5, "reader": "on"}),
    ("settlement", {"session": "2026-09-10", "rows": [
        {"ticker": "ORCL", "action": "HEDGE", "unhedged_bp": -812.0,
         "realised_bp": -41.0, "value_added_bp": 771.0, "correct": True}]}),
]


class TestPages(unittest.TestCase):
    def test_builds_from_an_empty_ledger(self):
        pages = build_site([])
        self.assertEqual(len(pages), 5)
        for name, html in pages.items():
            self.assertIn("<!doctype html>", html, name)
        self.assertIn("No decisions recorded yet", pages["tonight.html"])
        self.assertIn("Nothing settled yet", pages["settled.html"])

    def test_decisions_render_on_the_tonight_page(self):
        pages = build_site(POPULATED)
        tonight = pages["tonight.html"]
        self.assertIn("ORCL", tonight)
        self.assertIn("event reader judged HEDGE", tonight)
        self.assertIn("model", tonight)

    def test_settlements_render_on_the_settled_page(self):
        settled = build_site(POPULATED)["settled.html"]
        self.assertIn("-812", settled)
        self.assertIn("+771 bp", settled)

    def test_states_what_is_not_claimed(self):
        pages = build_site([])
        index = " ".join(pages["index.html"].split())
        evidence = " ".join(pages["evidence.html"].split())
        self.assertIn("priced protection, not alpha", evidence)
        self.assertIn("makes no Sharpe claim", evidence)
        self.assertIn("not claimed", evidence)
        self.assertIn("paper only", evidence)
        self.assertIn("Not the night's risk", index)

    def test_reports_a_broken_chain_rather_than_hiding_it(self):
        with tempfile.TemporaryDirectory() as d:
            ledger_path = Path(d) / "ledger.jsonl"
            Ledger(ledger_path, b"t").append("decision", {"ticker": "X"})
            with mock.patch.object(config, "LEDGER_PATH", ledger_path), \
                 mock.patch.object(config, "secret", return_value=b"wrong"), \
                 mock.patch.object(report, "OUT_DIR", Path(d)):
                pages = {p.name: p.read_text() for p in report.build()}
        self.assertIn("CHAIN BROKEN", pages["tonight.html"])

    def test_no_em_dashes_in_page_templates(self):
        for name, html in build_site([]).items():
            self.assertNotIn("—", html, f"{name} contains an em dash")


class StalenessCase(unittest.TestCase):
    """A stopped scheduler leaves the last good night on the page, which reads as
    a working site. Settlement had been failing on every run and the pages said
    nothing, so the page now states how far behind the ledger is."""

    def _site(self, session: str, now: dt.datetime):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "ledger.jsonl"
            lg = Ledger(path, config.DEV_SECRET)
            lg.append("night_summary", {"session": session, "positions": 1,
                                        "hedged": 0, "window_hours": 17.5})
            with mock.patch.object(config, "LEDGER_PATH", path), \
                 mock.patch.object(config, "secret", return_value=config.DEV_SECRET):
                return report.Site(now=now)

    def test_the_current_session_is_not_flagged(self):
        # 2026-09-10 21:00Z is after that day's 20:00Z close.
        site = self._site("2026-09-10", dt.datetime(2026, 9, 10, 21, tzinfo=dt.timezone.utc))
        self.assertEqual(site.behind, 0)
        self.assertEqual(site.freshness, "")

    def test_the_hour_before_the_run_is_due_is_not_stale(self):
        """The decide cron is an hour after the close. Flagging at the close made
        the page read STALE nightly between 20:00Z and whenever the run landed."""
        site = self._site("2026-09-10", dt.datetime(2026, 9, 11, 20, 58,
                                                    tzinfo=dt.timezone.utc))
        self.assertEqual(site.behind, 0)

    def test_a_run_delayed_three_hours_is_not_stale(self):
        """GitHub delayed one of ours by 3h17m; that must not raise an alarm."""
        site = self._site("2026-09-10", dt.datetime(2026, 9, 11, 23, 30,
                                                    tzinfo=dt.timezone.utc))
        self.assertEqual(site.behind, 0)

    def test_past_the_grace_period_it_is_stale(self):
        site = self._site("2026-09-10", dt.datetime(2026, 9, 12, 0, 30,
                                                    tzinfo=dt.timezone.utc))
        self.assertEqual(site.behind, 1)

    def test_a_missed_run_is_stated_on_the_page(self):
        # Past the grace window on 09-10, so both 09-09 and 09-10 are genuinely due.
        site = self._site("2026-09-08", dt.datetime(2026, 9, 11, 1, tzinfo=dt.timezone.utc))
        self.assertEqual(site.behind, 2)            # 09-09 and 09-10 both missed
        self.assertIn("2 sessions behind", site.freshness)

    def test_holidays_do_not_count_as_missed_sessions(self):
        """Labor Day 2026 is 09-07. Friday 09-04 to Tuesday 09-08 is one session."""
        site = self._site("2026-09-04", dt.datetime(2026, 9, 9, 1, tzinfo=dt.timezone.utc))
        self.assertEqual(site.behind, 1)


class ProvenanceCase(unittest.TestCase):
    """The page must say when the night was decided, derived from the ledger's own
    timestamp for entries written before the field existed."""

    def _site(self, session: str, written: dt.datetime, body_extra=None):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "ledger.jsonl"
            lg = Ledger(path, config.DEV_SECRET)
            body = {"session": session, "positions": 1, "hedged": 0, "window_hours": 17.5}
            body.update(body_extra or {})
            lg.append("night_summary", body, written)
            with mock.patch.object(config, "LEDGER_PATH", path), \
                 mock.patch.object(config, "secret", return_value=config.DEV_SECRET):
                return report.Site(now=written)

    def test_a_prompt_decision_is_reported_plainly(self):
        site = self._site("2026-09-10",
                          dt.datetime(2026, 9, 10, 22, tzinfo=dt.timezone.utc))
        self.assertAlmostEqual(site.decided_after, 2.0, places=1)
        self.assertFalse(site.decided_late)
        self.assertIn("2.0 hours", site.provenance)
        self.assertNotIn("not an ex-ante decision", site.provenance)

    def test_a_window_mostly_gone_is_disclosed_on_the_page(self):
        # 12:45Z the next day is 16.75h after a 20:00Z close - the entry that shipped.
        site = self._site("2026-09-10",
                          dt.datetime(2026, 9, 11, 12, 45, tzinfo=dt.timezone.utc))
        self.assertTrue(site.decided_late)
        self.assertIn("not an ex-ante decision", site.provenance)

    def test_a_recorded_lag_is_preferred_over_the_derived_one(self):
        site = self._site("2026-09-10",
                          dt.datetime(2026, 9, 11, 12, 45, tzinfo=dt.timezone.utc),
                          {"decided_after_close_hours": 1.5})
        self.assertEqual(site.decided_after, 1.5)
        self.assertFalse(site.decided_late)


class LandingWidgetCase(unittest.TestCase):
    """The policy declines about ten nights in twelve, so book order put five
    refusals in the landing page's only live widget and neither hedge - it read
    as a system that does nothing."""

    def _index(self, actions):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "ledger.jsonl"
            lg = Ledger(path, config.DEV_SECRET)
            lg.append("night_summary", {"session": "2026-09-10", "positions": len(actions),
                                        "hedged": sum(a == "HEDGE" for a in actions),
                                        "window_hours": 17.5})
            for ticker, action in actions.items():
                lg.append("decision", {"session": "2026-09-10", "ticker": ticker,
                                       "action": action, "sigma_bp": 100.0,
                                       "notional_usdt": 1000.0, "rationale": "x"})
            with mock.patch.object(config, "LEDGER_PATH", path), \
                 mock.patch.object(config, "secret", return_value=config.DEV_SECRET):
                site = report.Site(now=dt.datetime(2026, 9, 10, 21,
                                                   tzinfo=dt.timezone.utc))
                return site.index()

    def test_hedges_appear_before_refusals(self):
        actions = {t: "NO_HEDGE" for t in
                   ("TSLA", "NVDA", "PLTR", "COIN", "AMD", "MSFT")}
        actions["ORCL"] = "HEDGE"
        rows = re.findall(r'<div class="term-r">.*?</div>', self._index(actions))
        self.assertIn("ORCL", rows[0])

    def test_five_rows_do_not_misrepresent_twelve(self):
        actions = {t: "NO_HEDGE" for t in
                   ("TSLA", "NVDA", "PLTR", "COIN", "AMD", "MSFT")}
        actions["ORCL"] = "HEDGE"
        html = self._index(actions)
        self.assertIn("7 positions \u00b7 1 hedged", html)

    def test_a_short_night_needs_no_count_line(self):
        html = self._index({"ORCL": "HEDGE", "TSLA": "NO_HEDGE"})
        self.assertNotIn("see all", html)


class TileScopeCase(unittest.TestCase):
    """Tiles measure only sessions decided with the corrected calendar - a session
    whose hedges were a night early cannot say how well a hedge works. Excluding it
    raises the mean, so the scope note has to carry the sample size."""

    def _site(self, sessions):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "ledger.jsonl"
            lg = Ledger(path, config.DEV_SECRET)
            for session, va in sessions.items():
                lg.append("night_summary", {"session": session, "positions": 1,
                                            "hedged": 1, "window_hours": 17.5})
                lg.append("settlement", {"session": session, "decisions": 1, "hedged": 1,
                                         "rows": [{"ticker": "ORCL", "action": "HEDGE",
                                                   "unhedged_bp": -400.0, "realised_bp": -10.0,
                                                   "value_added_bp": va}]})
            with mock.patch.object(config, "LEDGER_PATH", path), \
                 mock.patch.object(config, "secret", return_value=config.DEV_SECRET):
                return report.Site(now=dt.datetime(2026, 9, 12, 21,
                                                   tzinfo=dt.timezone.utc))

    def test_only_the_affected_hedges_leave_the_tiles(self):
        site = self._site({"2026-09-09": -900.0, "2026-09-10": 300.0})
        self.assertEqual(len(site.clean), 1)
        self.assertEqual(site.mean_va, 300.0)          # not the -300 average of both
        self.assertEqual(len(site.hedges), 1)

    def test_a_refusal_on_an_affected_night_still_counts(self):
        """The fault could add a hedge, never remove one, so a refusal that night
        would have been a refusal under the corrected rule too. Excluding it would
        drop a sound decision and overstate the result."""
        row = {"ticker": "MU", "action": "NO_HEDGE", "unhedged_bp": -413.0,
               "realised_bp": -413.0, "value_added_bp": -395.0, "session": "2026-09-09"}
        self.assertFalse(report._selector_affected(row))
        row["action"] = "HEDGE"
        self.assertTrue(report._selector_affected(row))
        row["session"] = "2026-09-10"
        self.assertFalse(report._selector_affected(row))

    def test_it_stays_in_the_table(self):
        site = self._site({"2026-09-09": -900.0, "2026-09-10": 300.0})
        self.assertEqual(len(site.rows), 2, "an excluded row was dropped from the record")
        self.assertIn("2026-09-09", report._settled(site.rows))

    def test_the_scope_note_names_the_excluded_rows(self):
        flat = " ".join(self._site({"2026-09-09": -900.0,
                                    "2026-09-10": 300.0}).tile_scope.split())
        self.assertIn("1 hedges are excluded", flat.replace("1 hedges", "1 hedges"))
        self.assertIn("2026-09-09", flat)
        self.assertIn("refusals that night stand", flat)

    def test_no_scope_note_without_an_exclusion(self):
        flat = " ".join(self._site({"2026-09-10": 300.0}).tile_scope.split())
        self.assertNotIn("excluded", flat)
        self.assertIn("1 night", flat)

    def test_the_marker_reads_as_what_happened(self):
        html = report._settled([{"ticker": "ORCL", "action": "HEDGE",
                                 "unhedged_bp": -390.0, "realised_bp": -14.0,
                                 "value_added_bp": 376.0, "session": "2026-09-09"}])
        self.assertIn("hedged a night early", html)


class ProvenanceCase(unittest.TestCase):
    """The instrument claim is only true while every price really does come from
    the traded books. A test, not a sentence, because the sentence is the risk."""

    def _site(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "ledger.jsonl"
            Ledger(path, config.DEV_SECRET).append("night_summary", {"session": "2026-09-10"})
            with mock.patch.object(config, "LEDGER_PATH", path), \
                 mock.patch.object(config, "secret", return_value=config.DEV_SECRET):
                return report.Site(now=dt.datetime(2026, 9, 10, 21,
                                                   tzinfo=dt.timezone.utc))

    def test_no_price_source_outside_bitget(self):
        """The page states there is no equity feed. Verify it against the code."""
        market = (Path(__file__).resolve().parent.parent / "ballast" / "market.py").read_text()
        hosts = set(re.findall(r"https://([a-z0-9.]+)", market))
        self.assertEqual(hosts, {"api.bitget.com"}, f"market.py reaches {hosts}")

    def test_the_block_names_every_source_and_its_job(self):
        block = self._site().provenance_block
        for source in ("Bitget spot", "Bitget USDT-futures", "Nasdaq",
                       "Google News", "Qwen"):
            self.assertIn(source, block)
        self.assertIn("dates only, never a price", block)

    def test_it_states_the_instrument_distinction(self):
        # Normalised: the source wraps, so a line break can fall mid-phrase.
        flat = " ".join(self._site().provenance_block.split())
        self.assertIn("trades continuously", flat)
        self.assertIn("no equity feed anywhere in the codebase", flat)

    def test_it_is_on_the_evidence_page(self):
        site = self._site()
        self.assertIn(site.provenance_block, site.evidence_page())


class SettledTableCase(unittest.TestCase):
    """Two nights in, the table showed ORCL twice with near-identical numbers and
    nothing to tell them apart - which reads as a duplicate-row bug."""

    def test_every_row_names_its_session(self):
        rows = [{"ticker": "ORCL", "action": "HEDGE", "unhedged_bp": -390.0,
                 "realised_bp": -14.0, "value_added_bp": 376.0, "session": "2026-09-09"},
                {"ticker": "ORCL", "action": "HEDGE", "unhedged_bp": -384.0,
                 "realised_bp": -11.0, "value_added_bp": 373.0, "session": "2026-09-10"}]
        html = report._settled(rows)
        self.assertIn("2026-09-09", html)
        self.assertIn("2026-09-10", html)
        self.assertIn('data-label="Session"', html)

    def test_rows_group_by_night_newest_first(self):
        rows = [{"ticker": "SMALL", "action": "NO_HEDGE", "unhedged_bp": -10.0,
                 "realised_bp": -10.0, "value_added_bp": -5.0, "session": "2026-09-10"},
                {"ticker": "BIG", "action": "NO_HEDGE", "unhedged_bp": -900.0,
                 "realised_bp": -900.0, "value_added_bp": -880.0, "session": "2026-09-09"}]
        order = re.findall(r"<strong>([A-Z]+)</strong>", report._settled(rows))
        self.assertEqual(order, ["SMALL", "BIG"], "a bigger move from an older night led")


class SelectorMarkCase(unittest.TestCase):
    """A results page needs to say which rows are unsound, not why the bug happened.

    The mechanism is written up once, under defects. A hundred-word post-mortem in a
    callout here repeated what the tile scope note already said - the same
    duplication the roadmap callout was removed for.
    """

    def _rows(self, session):
        return [{"ticker": "ORCL", "action": "HEDGE", "unhedged_bp": -390.0,
                 "realised_bp": -14.0, "value_added_bp": 376.0, "session": session}]

    def test_an_affected_row_is_marked(self):
        html = report._settled(self._rows("2026-09-09"))
        self.assertIn("hedged a night early", html)

    def test_a_refusal_on_the_same_night_is_not_marked(self):
        rows = self._rows("2026-09-09")
        rows[0]["action"] = "NO_HEDGE"
        self.assertNotIn("hedged a night early", report._settled(rows))

    def test_a_clean_row_is_not(self):
        html = report._settled(self._rows("2026-09-10"))
        self.assertNotIn("hedged a night early", html)

    def test_the_page_points_at_the_full_write_up_rather_than_repeating_it(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "ledger.jsonl"
            lg = Ledger(path, config.DEV_SECRET)
            lg.append("night_summary", {"session": "2026-09-09", "positions": 1,
                                        "hedged": 1, "window_hours": 17.5})
            lg.append("settlement", {"session": "2026-09-09", "decisions": 1,
                                     "hedged": 1, "rows": self._rows("2026-09-09")})
            with mock.patch.object(config, "LEDGER_PATH", path), \
                 mock.patch.object(config, "secret", return_value=config.DEV_SECRET):
                page = report.Site(now=dt.datetime(2026, 9, 10, 21,
                                                   tzinfo=dt.timezone.utc)).settled_page()
        self.assertIn("docs.html#defects", page)
        self.assertNotIn("The calendar rule matched", page)


class DevKeyBuildGuard(unittest.TestCase):
    """The command line must not publish pages without the real signing key.

    Verification runs at build time and its verdict is a fixed string in the
    HTML, so a development-key rebuild over a real-key ledger publishes
    "CHAIN BROKEN" about a ledger that is intact.
    """

    def test_refuses_without_a_signing_key(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(config.UnsignedError):
                config.refuse_dev_build()

    def test_refuses_with_only_the_development_key(self):
        with mock.patch.dict(os.environ, {"BALLAST_DEV_SECRET": "1"}, clear=True):
            with self.assertRaises(config.UnsignedError):
                config.refuse_dev_build()

    def test_allows_a_deliberate_local_preview(self):
        env = {"BALLAST_DEV_SECRET": "1", config.DEV_BUILD_OVERRIDE: "1"}
        with mock.patch.dict(os.environ, env, clear=True):
            config.refuse_dev_build()

    def test_allows_a_real_key(self):
        with mock.patch.dict(os.environ, {"BALLAST_SECRET": "x"}, clear=True):
            config.refuse_dev_build()
