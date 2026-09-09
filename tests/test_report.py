"""The judge-facing report must build from any ledger state, including an empty one.

A demo that 500s on the day is worth less than no demo, and the handbook makes an
accessible demo a required material.
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from ballast import config, report
from ballast.ledger import Ledger


class TestReport(unittest.TestCase):
    def _build_with(self, entries) -> str:
        with tempfile.TemporaryDirectory() as d:
            ledger_path = Path(d) / "ledger.jsonl"
            out = Path(d) / "index.html"
            lg = Ledger(ledger_path, b"t")
            for kind, body in entries:
                lg.append(kind, body)
            with mock.patch.object(config, "LEDGER_PATH", ledger_path), \
                 mock.patch.object(config, "secret", return_value=b"t"), \
                 mock.patch.object(report, "OUT", out):
                return report.build().read_text()

    def test_builds_from_an_empty_ledger(self):
        page = self._build_with([])
        self.assertIn("<!doctype html>", page)
        self.assertIn("No decisions recorded yet", page)

    def test_renders_decisions_and_settlements(self):
        page = self._build_with([
            ("decision", {"ticker": "ORCL", "session": "2026-09-10", "action": "HEDGE",
                          "sigma_bp": 240.0, "notional_usdt": 1000.0,
                          "rationale": "event reader judged HEDGE",
                          "inputs": {"decided_by": "model"}}),
            ("night_summary", {"session": "2026-09-10", "positions": 1, "hedged": 1,
                               "window_hours": 17.5, "reader": "on"}),
            ("settlement", {"session": "2026-09-10", "rows": [
                {"ticker": "ORCL", "action": "HEDGE", "unhedged_bp": -812.0,
                 "realised_bp": -41.0, "value_added_bp": 771.0, "correct": True}]}),
        ])
        self.assertIn("ORCL", page)
        self.assertIn("-812", page)
        self.assertIn("+771 bp", page)
        self.assertIn("model", page)

    def test_states_what_is_not_claimed(self):
        # Normalise whitespace: the assertion is about the words, not where the
        # HTML source happens to wrap.
        page = " ".join(self._build_with([]).split())
        for phrase in ("not claimed", "paper only",
                       "priced protection, not alpha", "makes no Sharpe claim"):
            self.assertIn(phrase, page)

    def test_reports_a_broken_chain_rather_than_hiding_it(self):
        with tempfile.TemporaryDirectory() as d:
            ledger_path = Path(d) / "ledger.jsonl"
            out = Path(d) / "index.html"
            Ledger(ledger_path, b"t").append("decision", {"ticker": "X"})
            with mock.patch.object(config, "LEDGER_PATH", ledger_path), \
                 mock.patch.object(config, "secret", return_value=b"wrong"), \
                 mock.patch.object(report, "OUT", out):
                self.assertIn("CHAIN BROKEN", report.build().read_text())

    def test_is_self_contained(self):
        """No CDN, no fonts, no scripts — nothing that can fail on the day."""
        page = self._build_with([])
        for forbidden in ("<script", "http://", "cdn.", "fonts.googleapis"):
            self.assertNotIn(forbidden, page)


if __name__ == "__main__":
    unittest.main()
