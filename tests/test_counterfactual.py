"""The reader-vs-calendar comparison must be derived, checked, and not rewritten.

This page makes the sharpest claim in the project - that the model sometimes
changes the deterministic rule's answer - so the way that claim is computed carries
the same burden as the claim. Each test below stands for a way the comparison could
be quietly wrong: a counterfactual invented rather than derived, a derivation that
no longer matches the rule it stands in for, an attributable outcome credited to a
night the model did not decide, or a rebuild moving a figure an earlier build
published.
"""
from __future__ import annotations

import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path
from typing import ClassVar
from unittest import mock

from ballast import config, counterfactual, night, report
from ballast.ledger import Ledger
from ballast.policy import PolicyConfig


def decision(ticker: str, session: str, action: str, decided_by: str, **extra) -> tuple:
    body = {"ticker": ticker, "session": session, "action": action,
            "spot_symbol": f"R{ticker}USDT", "sigma_bp": 100.0,
            "rationale": f"{decided_by} said {action}",
            "inputs": {"decided_by": decided_by}}
    body.update(extra)
    return ("decision", body)


class Case(unittest.TestCase):
    """A throwaway ledger and a calendar stub, so nothing touches the network."""

    flagged: ClassVar[set] = set()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.ledger_path = self.root / "ledger.jsonl"
        self.patches = [
            mock.patch.object(config, "LEDGER_PATH", self.ledger_path),
            mock.patch.object(config, "STATE", self.root),
            mock.patch.object(config, "secret", return_value=b"t"),
            mock.patch.object(night, "scheduled_in_window", self._calendar),
        ]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in reversed(self.patches):
            p.stop()
        self.tmp.cleanup()

    def _calendar(self, ticker: str, session: dt.date) -> str | None:
        return "time-after-hours" if (ticker, session.isoformat()) in self.flagged else None

    def write(self, entries):
        lg = Ledger(self.ledger_path, b"t")
        for kind, body in entries:
            lg.append(kind, body)

    def build(self) -> dict:
        counterfactual.build()
        return counterfactual.load()


class TheCalendarCounterfactual(Case):
    def test_a_scheduled_report_is_the_rule_hedging(self):
        self.flagged = {("ORCL", "2026-09-10")}
        call = night.calendar_call("ORCL", dt.date(2026, 9, 10))
        self.assertEqual(call["action"], "HEDGE")
        self.assertTrue(call["flagged"])
        self.assertEqual(call["flag"], "time-after-hours")

    def test_an_empty_calendar_is_the_rule_declining(self):
        self.flagged = set()
        call = night.calendar_call("ORCL", dt.date(2026, 9, 10))
        self.assertEqual(call["action"], "NO_HEDGE")
        self.assertFalse(call["flagged"])
        self.assertIsNone(call["flag"])

    def test_it_refuses_to_answer_once_the_volatility_gate_is_on(self):
        """With the gate on the rule is no longer a function of the calendar alone.

        Returning NO_HEDGE anyway would look exactly like a correct answer and be
        a guess, so the row is dropped instead.
        """
        cfg = PolicyConfig(vol_gate_enabled=True)
        self.assertIsNone(night.calendar_call("ORCL", dt.date(2026, 9, 10), cfg)["action"])
        self.assertEqual(counterfactual.calendar_action("ORCL", dt.date(2026, 9, 10), cfg),
                         (None, None))

    def test_the_index_drops_rows_it_cannot_decide(self):
        self.write([decision("ORCL", "2026-09-10", "HEDGE", "model")])
        with mock.patch.object(night, "DEFAULT_POLICY",
                               PolicyConfig(vol_gate_enabled=True)):
            self.assertEqual(self.build()["rows"], [])


class WhatCountsAsAnOverride(Case):
    def test_a_model_hedge_the_calendar_would_not_have_taken_is_a_flip(self):
        self.write([decision("COIN", "2026-09-15", "HEDGE", "model")])
        out = self.build()
        self.assertEqual(out["counts"]["flips"], 1)
        self.assertEqual(out["counts"]["flips_to_hedge"], 1)
        self.assertEqual(out["counts"]["flips_to_no_hedge"], 0)
        self.assertEqual(out["rows"][0]["calendar"], "NO_HEDGE")

    def test_a_model_refusal_the_calendar_would_have_hedged_is_a_flip(self):
        self.flagged = {("ORCL", "2026-09-10")}
        self.write([decision("ORCL", "2026-09-10", "NO_HEDGE", "model")])
        out = self.build()
        self.assertEqual(out["counts"]["flips_to_no_hedge"], 1)
        self.assertEqual(out["counts"]["flips_to_hedge"], 0)

    def test_agreement_is_not_an_override(self):
        self.write([decision("NVDA", "2026-09-15", "NO_HEDGE", "model")])
        out = self.build()
        self.assertEqual(out["counts"]["flips"], 0)
        self.assertEqual(out["counts"]["agreed"], 1)

    def test_every_flip_is_one_direction_or_the_other(self):
        self.flagged = {("ORCL", "2026-09-10")}
        self.write([decision("COIN", "2026-09-15", "HEDGE", "model"),
                    decision("ORCL", "2026-09-10", "NO_HEDGE", "model"),
                    decision("NVDA", "2026-09-15", "NO_HEDGE", "model")])
        c = self.build()["counts"]
        self.assertEqual(c["flips"], c["flips_to_hedge"] + c["flips_to_no_hedge"])
        self.assertEqual(c["flips"] + c["agreed"], c["model"])

    def test_a_position_with_no_decision_taken_is_not_compared(self):
        """A market-data failure is recorded as a row; it is not a model call."""
        self.write([decision("MU", "2026-09-15", "NO_HEDGE", "none")])
        self.assertEqual(self.build()["rows"], [])


class TheDerivationIsChecked(Case):
    def test_a_rule_row_that_disagrees_is_published_as_a_mismatch(self):
        """A rule-decided row IS the calendar's answer, so it tests the derivation."""
        self.write([decision("ORCL", "2026-09-09", "HEDGE", "rule")])
        check = self.build()["check"]
        self.assertEqual(check["rule_rows"], 1)
        self.assertEqual(check["matched"], 0)
        self.assertEqual(check["mismatched"][0]["ticker"], "ORCL")
        self.assertEqual(check["mismatched"][0]["recorded"], "HEDGE")
        self.assertEqual(check["mismatched"][0]["derived"], "NO_HEDGE")

    def test_a_rule_row_that_agrees_is_counted_as_a_match(self):
        self.write([decision("NVDA", "2026-09-15", "NO_HEDGE", "rule")])
        check = self.build()["check"]
        self.assertEqual((check["rule_rows"], check["matched"], check["mismatched"]),
                         (1, 1, []))


class TheSelectorDefect(Case):
    def test_a_hedge_on_an_affected_session_is_marked_and_left_out_of_the_counts(self):
        self.write([decision("ADBE", "2026-09-09", "HEDGE", "model")])
        out = self.build()
        self.assertTrue(out["rows"][0]["selector_affected"])
        self.assertEqual(out["counts"]["flips"], 0)
        self.assertEqual(out["counts"]["excluded"], 1)
        self.assertEqual(out["counts"]["compared"], 0)

    def test_a_refusal_on_an_affected_session_is_not_marked(self):
        """The old rule could add a hedge, never remove one."""
        self.write([decision("NVDA", "2026-09-09", "NO_HEDGE", "model")])
        out = self.build()
        self.assertFalse(out["rows"][0]["selector_affected"])
        self.assertEqual(out["counts"]["excluded"], 0)


class TheProvenanceOfEachRow(Case):
    def test_a_calendar_call_recorded_at_decision_time_wins(self):
        """The live run saw a release-time flag a later re-derivation cannot."""
        self.write([decision("ORCL", "2026-09-10", "HEDGE", "model",
                             calendar={"flagged": True, "flag": "time-after-hours",
                                       "action": "HEDGE"})])
        row = self.build()["rows"][0]
        self.assertEqual((row["source"], row["calendar"], row["flip"]),
                         ("recorded", "HEDGE", False))

    def test_a_derived_row_is_pinned_and_not_rewritten_by_a_later_build(self):
        """A public feed moving must not silently restate what was published."""
        self.write([decision("COIN", "2026-09-15", "HEDGE", "model")])
        self.assertEqual(self.build()["rows"][0]["calendar"], "NO_HEDGE")
        self.flagged = {("COIN", "2026-09-15")}          # Nasdaq now says otherwise
        out = self.build()
        self.assertEqual(out["rows"][0]["calendar"], "NO_HEDGE")
        self.assertEqual(out["counts"]["flips"], 1)

    def test_a_recorded_call_overrides_a_pin(self):
        self.write([decision("COIN", "2026-09-15", "HEDGE", "model")])
        self.build()
        self.ledger_path.unlink()
        self.write([decision("COIN", "2026-09-15", "HEDGE", "model",
                             calendar={"flagged": True, "flag": "time-after-hours",
                                       "action": "HEDGE"})])
        row = self.build()["rows"][0]
        self.assertEqual((row["source"], row["calendar"]), ("recorded", "HEDGE"))


class OnlyOverridesAreAttributable(Case):
    def test_value_added_is_summed_over_flips_alone(self):
        self.write([
            decision("COIN", "2026-09-15", "HEDGE", "model"),
            decision("NVDA", "2026-09-15", "NO_HEDGE", "model"),
            ("settlement", {"session": "2026-09-15", "rows": [
                {"ticker": "COIN", "action": "HEDGE", "value_added_bp": 104.0},
                {"ticker": "NVDA", "action": "NO_HEDGE", "value_added_bp": -900.0}]}),
        ])
        out = self.build()
        self.assertEqual(out["flip_value_added_bp"], 104.0)
        self.assertEqual(out["flips_settled"], 1)

    def test_an_unsettled_flip_contributes_nothing(self):
        self.write([decision("COIN", "2026-09-18", "HEDGE", "model")])
        out = self.build()
        self.assertIsNone(out["flip_value_added_bp"])
        self.assertEqual(out["flips_settled"], 0)
        self.assertIsNone(out["rows"][0]["value_added_bp"])


class TheNightlyRunRecordsIt(Case):
    def test_the_decision_record_carries_the_rules_own_answer(self):
        self.flagged = {("ORCL", "2026-09-10")}
        record = night.calendar_call("ORCL", dt.date(2026, 9, 10))
        self.assertEqual(set(record), {"flagged", "flag", "action"})
        self.assertTrue(json.dumps(record))          # must survive the ledger


class ThePage(Case):
    def page(self) -> str:
        site = report.Site()
        return site.reader_page()

    def test_it_renders_without_an_index(self):
        self.write([decision("COIN", "2026-09-15", "HEDGE", "model")])
        self.assertIn("has not been built yet", self.page())

    def test_an_override_reaches_the_page_with_what_the_model_read(self):
        self.write([decision("COIN", "2026-09-15", "HEDGE", "model",
                             reader={"verbatim_quote": "Senate rejects Clarity Act"})])
        self.build()
        out = self.page()
        self.assertIn("Senate rejects Clarity Act", out)
        self.assertIn("1 of 1", out)

    def test_it_says_so_plainly_when_the_model_never_disagrees(self):
        self.write([decision("NVDA", "2026-09-15", "NO_HEDGE", "model")])
        self.build()
        out = self.page()
        self.assertIn("not once changed the rule's answer", out)
        self.assertIn("reporting, not deciding", out)

    def test_a_loss_on_the_overrides_is_published_as_a_loss(self):
        self.write([
            decision("MU", "2026-09-14", "HEDGE", "model"),
            ("settlement", {"session": "2026-09-14", "rows": [
                {"ticker": "MU", "action": "HEDGE", "value_added_bp": -117.4}]}),
        ])
        self.build()
        out = self.page()
        self.assertIn("cost", out)
        self.assertIn("117 bp", out)
        self.assertNotIn("added <strong>117", out)


if __name__ == "__main__":
    unittest.main()
