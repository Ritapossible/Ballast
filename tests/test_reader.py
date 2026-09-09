"""The reader's gates.

The model owns the hedge judgment, so the gates around it are the only thing
standing between a hallucinated headline and a real order. Each test drives a
specific failure and asserts the specific gate that caught it.

No network and no API key: `llm.complete` is replaced per test.
"""
from __future__ import annotations

import datetime as dt
import json
import unittest
from unittest import mock

from ballast import llm, reader
from ballast.news import NewsItem
from ballast.policy import Action, EventType, Impact, decide
from ballast.reader import Judgment, RejectReason, read

SESSION = dt.date(2026, 9, 10)
HEADLINE = "Oracle Earnings Preview: RPO and Cash Flow in Focus"
ITEMS = [NewsItem(title=HEADLINE, url="https://example.com/orcl",
                  source="Test Wire",
                  published=dt.datetime(2026, 9, 10, 21, 0, tzinfo=dt.timezone.utc))]


def answer(**overrides) -> str:
    body = {"ticker": "ORCL", "judgment": "HEDGE", "event_type": "earnings",
            "expected_impact": "high", "confidence": 0.9,
            "verbatim_quote": HEADLINE, "reasoning": "Reports tonight.",
            "unknowns": []}
    body.update(overrides)
    return json.dumps(body)


def with_response(text: str):
    return mock.patch.object(
        llm, "complete",
        return_value=llm.Completion(text=text, model="qwen3.8-max"))


def with_key():
    return mock.patch.object(llm, "available", return_value=True)


class TestAcceptance(unittest.TestCase):
    def test_grounded_hedge_is_accepted(self):
        with with_key(), with_response(answer()):
            v = read("ORCL", SESSION, 17.5, ITEMS, True)
        self.assertTrue(v.accepted)
        self.assertIs(v.judgment, Judgment.HEDGE)
        self.assertEqual(v.risk.verbatim_quote, HEADLINE)
        self.assertEqual(v.risk.source_url, "https://example.com/orcl")

    def test_no_hedge_is_accepted_and_usable(self):
        with with_key(), with_response(answer(judgment="NO_HEDGE", event_type="none",
                                              expected_impact="low", verbatim_quote="")):
            v = read("ORCL", SESSION, 17.5, ITEMS, False)
        self.assertTrue(v.accepted)
        self.assertTrue(v.usable)

    def test_fenced_json_is_tolerated(self):
        with with_key(), with_response(f"```json\n{answer()}\n```"):
            self.assertTrue(read("ORCL", SESSION, 17.5, ITEMS, True).accepted)


class TestGates(unittest.TestCase):
    def test_missing_key_abstains(self):
        with mock.patch.object(llm, "available", return_value=False):
            v = read("ORCL", SESSION, 17.5, ITEMS, True)
        self.assertIs(v.rejected_because, RejectReason.NO_MODEL)
        self.assertFalse(v.usable)

    def test_unparseable_output_is_refused(self):
        with with_key(), with_response("I think you should probably hedge this one."):
            v = read("ORCL", SESSION, 17.5, ITEMS, True)
        self.assertIs(v.rejected_because, RejectReason.BAD_SCHEMA)

    def test_invalid_enum_is_refused(self):
        with with_key(), with_response(answer(judgment="MAYBE")):
            self.assertIs(read("ORCL", SESSION, 17.5, ITEMS, True).rejected_because,
                          RejectReason.BAD_SCHEMA)

    def test_answer_about_another_ticker_is_refused(self):
        """P13: a judgment about a different instrument is never usable."""
        with with_key(), with_response(answer(ticker="NVDA")):
            self.assertIs(read("ORCL", SESSION, 17.5, ITEMS, True).rejected_because,
                          RejectReason.WRONG_TICKER)

    def test_fabricated_quote_is_refused(self):
        """The grounding gate — the one that catches an invented source."""
        with with_key(), with_response(
                answer(verbatim_quote="Oracle announces surprise 40% dividend cut")):
            self.assertIs(read("ORCL", SESSION, 17.5, ITEMS, True).rejected_because,
                          RejectReason.UNGROUNDED)

    def test_hedge_with_no_quote_and_no_calendar_is_refused(self):
        with with_key(), with_response(answer(verbatim_quote="")):
            self.assertIs(read("ORCL", SESSION, 17.5, ITEMS, False).rejected_because,
                          RejectReason.UNGROUNDED)

    def test_low_confidence_hedge_is_refused(self):
        with with_key(), with_response(answer(confidence=0.2)):
            self.assertIs(read("ORCL", SESSION, 17.5, ITEMS, True).rejected_because,
                          RejectReason.LOW_CONFIDENCE)

    def test_abstain_is_not_usable(self):
        with with_key(), with_response(answer(judgment="ABSTAIN", verbatim_quote="")):
            v = read("ORCL", SESSION, 17.5, ITEMS, True)
        self.assertTrue(v.accepted)
        self.assertFalse(v.usable)

    def test_endpoint_failure_abstains_rather_than_guessing(self):
        with with_key(), mock.patch.object(
                llm, "complete", side_effect=llm.LLMUnavailable("HTTP 500")):
            self.assertIs(read("ORCL", SESSION, 17.5, ITEMS, True).rejected_because,
                          RejectReason.NO_MODEL)


class TestAuthorityBoundary(unittest.TestCase):
    """The model owns the judgment and nothing else."""

    def test_model_hedge_leads_over_a_quiet_calendar(self):
        d = decide("X", "RXUSDT", [0.001] * 60,
                   reader.NightRisk(ticker="X", event_type=EventType.LEGAL,
                                    expected_impact=Impact.HIGH, confidence=0.9),
                   17.5, model_judgment="HEDGE")
        self.assertIs(d.action, Action.HEDGE)
        self.assertEqual(d.inputs["decided_by"], "model")

    def test_model_no_hedge_leads_over_scheduled_earnings(self):
        earnings = reader.NightRisk(ticker="X", event_type=EventType.EARNINGS,
                                    expected_impact=Impact.HIGH, confidence=1.0)
        d = decide("X", "RXUSDT", [0.001] * 60, earnings, 17.5,
                   model_judgment="NO_HEDGE")
        self.assertIs(d.action, Action.NO_HEDGE)

    def test_abstention_falls_back_to_the_calendar_rule(self):
        earnings = reader.NightRisk(ticker="X", event_type=EventType.EARNINGS,
                                    expected_impact=Impact.HIGH, confidence=1.0)
        d = decide("X", "RXUSDT", [0.001] * 60, earnings, 17.5, model_judgment=None)
        self.assertIs(d.action, Action.HEDGE)
        self.assertEqual(d.inputs["decided_by"], "rule")

    def test_the_verdict_carries_no_size_or_direction(self):
        for field in ("notional", "size", "side", "quantity", "price"):
            self.assertNotIn(field, reader.ReaderVerdict.__dataclass_fields__)


if __name__ == "__main__":
    unittest.main()
