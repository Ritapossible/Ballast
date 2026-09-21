"""The readers that decide whether bitget-signal answered with anything.

The whole point of this module is that "answered" and "carried data" are
different, and that the difference is invisible unless something measures it.
Three shapes from the live service are fixtures here, verbatim, because each one
defeats an obvious implementation:

  * `{"error": ""}` - answered, carried nothing, raised nothing.
  * the yield curve - a computed conclusion sitting on top of six failures.
  * `news_feed` - 44 envelopes that count as 44 "headlines" if you count wrong.
"""
import json
import unittest
from pathlib import Path
from unittest import mock

from ballast import mcp, signal_probe

# Verbatim from datahub.noxiaohao.com/mcp on 2026-09-21.
YIELD_CURVE_ALL_FAILED = {
    "yield_curve": {"t3m": {"error": ""}, "t1y": {"error": ""}, "t2y": {"error": ""},
                    "t5y": {"error": ""}, "t10y": {"error": ""}, "t30y": {"error": ""}},
    "spread_10y2y": 0.0, "inverted": False,
    "note": "Inverted yield curve (10Y < 2Y) historically precedes recession",
}
RSI_AAPL = {"symbol": "AAPL", "timeframe": "4h", "rsi": 64.47, "period": 14,
            "signal": "neutral"}
RSI_REFUSED = {"error": "No OHLCV data for ZZZZQQ/4h"}
DEAD_FEEDS = [{"feed": "cointelegraph", "error": "", "items": []},
              {"feed": "cnbc", "error": "", "items": []}]


class TheYieldCurveDoesNotGetToConcludeAnything(unittest.TestCase):
    def test_a_curve_whose_every_maturity_failed_carries_no_data(self):
        """`spread_10y2y: 0.0` and `inverted: false` are computed, not observed.

        Counting top-level keys scores this row as carrying data, which is how a
        service returning nothing gets published as a recession signal.
        """
        self.assertEqual(signal_probe._numeric_yields(YIELD_CURVE_ALL_FAILED), 0)

    def test_a_curve_that_resolved_is_counted(self):
        live = json.loads(json.dumps(YIELD_CURVE_ALL_FAILED))
        live["yield_curve"]["t10y"] = 4.11
        live["yield_curve"]["t2y"] = 3.86
        self.assertEqual(signal_probe._numeric_yields(live), 2)


class EmptyEnvelopesAreNotData(unittest.TestCase):
    def test_the_shapes_the_service_actually_returns_all_count_as_nothing(self):
        for payload in ({"error": ""}, {"alt_me_error": ""},
                        {"text": "Error executing tool crypto_price: ConnectTimeout('')"},
                        {}):
            with self.subTest(payload=payload):
                self.assertEqual(signal_probe._anything(payload), 0,
                                 f"{payload} was scored as data")

    def test_a_real_answer_counts(self):
        self.assertEqual(signal_probe._anything({"cpi": 3.1, "released": "2026-09-11"}), 2)

    def test_a_note_alone_is_not_an_answer(self):
        """Every one of these tools ships an explanatory `note` regardless of
        whether the fetch behind it worked."""
        self.assertEqual(signal_probe._anything({"note": "how to read this", "error": ""}), 0)


class IndicatorsAreOnlyEvidenceIfNonsenseIsRefused(unittest.TestCase):
    def test_a_real_indicator_is_counted(self):
        self.assertEqual(signal_probe._indicator(RSI_AAPL), 1)

    def test_a_refusal_is_not(self):
        self.assertEqual(signal_probe._indicator(RSI_REFUSED), 0)

    def test_coverage_records_the_control_as_refused(self):
        """If the service ever answers for an invented ticker, every RSI it
        returns stops being evidence of anything. That has to be recorded, not
        assumed, because the page leans on it."""
        def answer(tool, **kw):
            return RSI_AAPL if kw.get("symbol") in ("MSFT", "NVDA") else RSI_REFUSED
        with mock.patch.object(mcp, "signal", side_effect=answer):
            out = signal_probe.coverage(["MSFT", "NVDA", "COST"])
        self.assertEqual(out["answered"], ["MSFT", "NVDA"])
        self.assertEqual(out["missing"], ["COST"])
        self.assertTrue(out["control_refused"])

    def test_a_service_that_answers_for_a_fake_ticker_is_recorded_as_such(self):
        with mock.patch.object(mcp, "signal", return_value=RSI_AAPL):
            out = signal_probe.coverage(["MSFT"])
        self.assertFalse(out["control_refused"],
                         "an invented ticker was answered and nothing noticed")


class FeedsAreNotHeadlines(unittest.TestCase):
    def test_forty_four_dead_envelopes_are_zero_articles(self):
        self.assertEqual(signal_probe._articles(DEAD_FEEDS), 0)

    def test_articles_are_counted_across_feeds(self):
        live = [{"feed": "cnbc", "error": "", "items": [{"title": "a"}, {"title": "b"}]},
                {"feed": "decrypt", "error": "", "items": [{"title": "c"}]}]
        self.assertEqual(signal_probe._articles(live), 3)


class UnreachableIsNotEmpty(unittest.TestCase):
    def test_a_service_that_cannot_be_reached_is_recorded_separately(self):
        """"We asked and it had nothing" and "we could not ask" are different
        findings. Collapsing them is how an outage gets published as a fact
        about the data."""
        with mock.patch.object(mcp, "signal",
                               side_effect=mcp.McpUnavailable("HTTP 503")):
            row = signal_probe._probe("news_feed", "latest", {},
                                      signal_probe._articles, "articles")
        self.assertEqual(row["verdict"], "unreachable")
        self.assertIsNone(row["count"])
        self.assertIn("503", row["detail"])

    def test_an_answered_but_empty_call_is_empty_not_unreachable(self):
        with mock.patch.object(mcp, "signal", return_value=DEAD_FEEDS):
            row = signal_probe._probe("news_feed", "latest", {},
                                      signal_probe._articles, "articles")
        self.assertEqual(row["verdict"], "empty")
        self.assertEqual(row["count"], 0)


class EveryProbeNamesAnAction(unittest.TestCase):
    def test_no_probe_is_left_to_default(self):
        """A bare call is answered, not rejected, and its answer looks empty.
        That is precisely the mistake this module was written to correct, so a
        probe without an action would reintroduce it."""
        for tool, action, *_ in signal_probe.PROBES:
            with self.subTest(tool=tool):
                self.assertTrue(action, f"{tool} is probed without an action")

    def test_the_committed_measurement_is_shaped_the_way_the_page_reads_it(self):
        path = Path(__file__).resolve().parent.parent / "state" / "signal_probe.json"
        d = json.loads(path.read_text())
        counts = d["counts"]
        self.assertEqual(counts["catalog_probed"] + counts["live_probed"],
                         counts["probed"], "the probe file does not add up")
        self.assertEqual(counts["with_data"] + counts["empty"] + counts["unreachable"],
                         counts["probed"], "verdicts do not account for every probe")
        self.assertIn("Unknown action", d["no_action_reply"],
                      "the recorded bare-call reply no longer shows the trap")


if __name__ == "__main__":
    unittest.main()
