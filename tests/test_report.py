"""The public pages must build from any ledger state, including an empty one.

A demo that errors on the day is worth less than no demo, and the handbook makes an
accessible demo a required material.
"""
from __future__ import annotations

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
