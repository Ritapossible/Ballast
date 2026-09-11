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

from ballast import llm, news, reader
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


class TestEndpointResilience(unittest.TestCase):
    """The first live run abstained on half its positions because the endpoint
    failed, and every one was logged identically to the model choosing to abstain.
    Retries reduce the first problem; carrying the reason fixes the second."""

    def test_transient_failures_are_retried(self):
        """Drives the real `complete`; the retry lives inside it, not around it."""
        import io
        import urllib.error
        attempts = {"n": 0}
        body = json.dumps({"choices": [{"message": {"content": answer()}}],
                           "model": "qwen3.8-max", "usage": {}}).encode()

        class Resp(io.BytesIO):
            def __enter__(self): return self
            def __exit__(self, *a): return False

        def flaky(req, timeout=None):
            attempts["n"] += 1
            if attempts["n"] < 3:
                raise urllib.error.HTTPError("u", 429, "Too Many", {}, None)
            return Resp(body)

        with mock.patch.dict("os.environ", {"QWEN_API_KEY": "k"}), \
             mock.patch.object(llm.urllib.request, "urlopen", flaky), \
             mock.patch.object(llm.time, "sleep"):
            completion = llm.complete("s", "u")
        self.assertEqual(attempts["n"], 3, "should have retried twice then succeeded")
        self.assertIn("ORCL", completion.text)

    def test_persistent_failure_reports_the_last_status(self):
        import urllib.error
        with mock.patch.dict("os.environ", {"QWEN_API_KEY": "k"}), \
             mock.patch.object(llm.urllib.request, "urlopen",
                               side_effect=urllib.error.HTTPError("u", 503, "x", {}, None)), \
             mock.patch.object(llm.time, "sleep"), \
             self.assertRaises(llm.LLMUnavailable) as ctx:
            llm.complete("s", "u")
        self.assertEqual(ctx.exception.detail, "HTTP 503")

    def test_retryable_statuses_are_distinguished_from_fatal_ones(self):
        self.assertIn(429, llm.RETRYABLE_STATUS)
        self.assertIn(503, llm.RETRYABLE_STATUS)
        self.assertNotIn(401, llm.RETRYABLE_STATUS)
        self.assertNotIn(400, llm.RETRYABLE_STATUS)

    def test_the_failure_reason_reaches_the_ledger(self):
        with with_key(), mock.patch.object(
                llm, "complete",
                side_effect=llm.LLMUnavailable("3 attempts failed, last: HTTP 429",
                                               "HTTP 429")):
            verdict = read("ORCL", SESSION, 17.5, ITEMS, True)
        self.assertIs(verdict.rejected_because, RejectReason.NO_MODEL)
        self.assertIn("HTTP 429", verdict.to_record()["unknowns"][0])

    def test_a_bad_key_is_not_retried(self):
        import urllib.error
        calls = {"n": 0}

        def unauthorised(*a, **k):
            calls["n"] += 1
            raise urllib.error.HTTPError("u", 401, "Unauthorized", {}, None)

        with mock.patch.dict("os.environ", {"QWEN_API_KEY": "bad"}), \
             mock.patch.object(llm.urllib.request, "urlopen", unauthorised), \
             mock.patch.object(llm.time, "sleep"), \
             self.assertRaises(llm.LLMUnavailable) as ctx:
            llm.complete("s", "u")
        self.assertEqual(calls["n"], 1, "a 401 must not be retried")
        self.assertEqual(ctx.exception.detail, "HTTP 401")


class NewsFailureIsDistinctCase(unittest.TestCase):
    """A DNS failure, an HTTP 500, a timeout and "nothing published tonight" all
    became an empty list. The reader then abstained for what looked like a
    legitimate reason, so the model half of the product could degrade across every
    name for days with nothing to show it."""

    def _raises(self, exc):
        return mock.patch.object(news.urllib.request, "urlopen", side_effect=exc)

    def test_an_http_error_is_not_an_empty_feed(self):
        err = news.urllib.error.HTTPError("u", 503, "down", None, None)
        with self._raises(err), self.assertRaises(news.NewsUnavailable) as caught:
            news.fetch("TSLA")
        self.assertIn("503", caught.exception.reason)

    def test_an_unreachable_host_is_not_an_empty_feed(self):
        with self._raises(news.urllib.error.URLError("no route")), \
             self.assertRaises(news.NewsUnavailable) as caught:
            news.fetch("TSLA")
        self.assertIn("unreachable", caught.exception.reason)

    def test_a_timeout_is_not_an_empty_feed(self):
        with self._raises(TimeoutError()), \
             self.assertRaises(news.NewsUnavailable) as caught:
            news.fetch("TSLA")
        self.assertIn("timeout", caught.exception.reason)

    def test_a_malformed_feed_is_not_an_empty_feed(self):
        resp = mock.MagicMock()
        resp.__enter__.return_value.read.return_value = b"<rss><unclosed>"
        with mock.patch.object(news.urllib.request, "urlopen", return_value=resp), \
             self.assertRaises(news.NewsUnavailable) as caught:
            news.fetch("TSLA")
        self.assertIn("malformed", caught.exception.reason)

    def test_a_genuinely_empty_feed_is_still_empty(self):
        """The distinction only matters if the ordinary case still works."""
        resp = mock.MagicMock()
        resp.__enter__.return_value.read.return_value = b"<rss><channel></channel></rss>"
        with mock.patch.object(news.urllib.request, "urlopen", return_value=resp):
            self.assertEqual(news.fetch("TSLA"), [])

    def test_the_night_records_why_the_feed_was_empty(self):
        from ballast import night
        with mock.patch.object(night, "fetch",
                               side_effect=news.NewsUnavailable("http 503")), \
             mock.patch.object(night, "calendar_risk",
                               return_value=(reader.NightRisk(ticker="TSLA"), False)), \
             mock.patch.object(night, "read") as fake_read:
            fake_read.return_value = mock.MagicMock(usable=False)
            _, _, _, provenance = night.assess("TSLA", dt.date(2026, 9, 10), True)
        self.assertEqual(provenance["source"], "unavailable")
        self.assertEqual(provenance["error"], "http 503")
