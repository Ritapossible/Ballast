"""The public pages must build from any ledger state, including an empty one.

A demo that errors on the day is worth less than no demo, and the handbook makes an
accessible demo a required material.
"""
from __future__ import annotations

import datetime as dt
import os
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

    def test_a_missed_run_is_stated_on_the_page(self):
        site = self._site("2026-09-08", dt.datetime(2026, 9, 10, 21, tzinfo=dt.timezone.utc))
        self.assertEqual(site.behind, 2)            # 09-09 and 09-10 both missed
        self.assertIn("2 sessions behind", site.freshness)

    def test_holidays_do_not_count_as_missed_sessions(self):
        """Labor Day 2026 is 09-07. Friday 09-04 to Tuesday 09-08 is one session."""
        site = self._site("2026-09-04", dt.datetime(2026, 9, 8, 21, tzinfo=dt.timezone.utc))
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


class SelectorCorrectionCase(unittest.TestCase):
    """The affected hedges are the ones the settled tiles are built from, so the
    correction has to sit beside them, not only in the defect list."""

    def _site(self, session: str):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "ledger.jsonl"
            lg = Ledger(path, config.DEV_SECRET)
            lg.append("night_summary", {"session": session, "positions": 1,
                                        "hedged": 1, "window_hours": 17.5})
            lg.append("settlement", {"session": session, "decisions": 1, "hedged": 1,
                                     "rows": [{"ticker": "ORCL", "action": "HEDGE",
                                               "unhedged_bp": -390.0, "realised_bp": -13.6,
                                               "counterfactual_bp": -390.0,
                                               "value_added_bp": 376.6}]})
            with mock.patch.object(config, "LEDGER_PATH", path), \
                 mock.patch.object(config, "secret", return_value=config.DEV_SECRET):
                return report.Site(now=dt.datetime(2026, 9, 11, 21,
                                                   tzinfo=dt.timezone.utc))

    def test_an_affected_session_carries_the_correction(self):
        site = self._site("2026-09-09")
        self.assertIn("ORCL", site.selector_correction)
        self.assertIn("a night early", site.selector_correction)
        self.assertIn(site.selector_correction, site.settled_page())

    def test_a_clean_session_carries_none(self):
        self.assertEqual(self._site("2026-09-10").selector_correction, "")


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
