"""The second calendar source must never turn silence into "no earnings".

The calendar selector is the one input the whole policy rests on, so a second
opinion that fails open is worse than no second opinion at all: it would report
agreement with Nasdaq on every night the service happened to be down. Each test
below stands for a way this could quietly go wrong.
"""
from __future__ import annotations

import datetime as dt
import json
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

from ballast import config, crosscheck, mcp
from ballast.ledger import Ledger


def sse(payload: dict) -> str:
    """The framing the live service actually answers with."""
    return "event: message\ndata: " + json.dumps(payload) + "\n\n"


def tool_result(obj) -> str:
    return sse({"jsonrpc": "2.0", "id": 2,
                "result": {"content": [{"type": "text", "text": json.dumps(obj)}]}})


class TheTransport(unittest.TestCase):
    def test_it_reads_server_sent_event_frames(self):
        self.assertEqual(mcp._unframe(sse({"a": 1})), {"a": 1})

    def test_it_still_reads_plain_json(self):
        self.assertEqual(mcp._unframe('{"a": 1}'), {"a": 1})

    def test_an_empty_body_is_not_a_crash(self):
        self.assertEqual(mcp._unframe("  "), {})


class TheCallContract(unittest.TestCase):
    def call_with(self, responses):
        """responses: list of (headers, body) returned in order."""
        it = iter(responses)
        with mock.patch.object(mcp, "_post", side_effect=lambda *a, **k: next(it)):
            return mcp.call("do_query", {"entry_id": "x", "params": {}}, retries=1)

    def test_a_successful_call_returns_the_parsed_payload(self):
        out = self.call_with([
            ({"mcp-session-id": "s"}, sse({"result": {}})),
            ({}, ""),
            ({}, tool_result({"rows": [1, 2]})),
        ])
        self.assertEqual(out, {"rows": [1, 2]})

    def test_no_session_id_is_refused(self):
        with self.assertRaises(mcp.McpUnavailable):
            self.call_with([({}, sse({"result": {}}))])

    def test_an_http_error_is_typed_not_swallowed(self):
        err = urllib.error.HTTPError(mcp.ENDPOINT, 404, "Not Found", {}, None)
        with mock.patch.object(mcp, "_post", side_effect=err), \
             self.assertRaises(mcp.McpUnavailable) as caught:
            mcp.call("guide", {}, retries=1)
        self.assertIn("404", caught.exception.reason)

    def test_an_upstream_failure_is_not_returned_as_data(self):
        """The tool answers 200 and wraps the upstream's own status.

        A 503 body parses perfectly well. Handed back as data it would become an
        empty result, and an empty result reads as "nothing scheduled tonight".
        """
        with self.assertRaises(mcp.McpUnavailable) as caught:
            self.call_with([
                ({"mcp-session-id": "s"}, sse({"result": {}})),
                ({}, ""),
                ({}, tool_result({"success": False, "status_code": 503,
                                  "data": "<html>503</html>", "error": None})),
            ])
        self.assertIn("503", caught.exception.reason)

    def test_an_empty_content_list_is_refused(self):
        with self.assertRaises(mcp.McpUnavailable):
            self.call_with([
                ({"mcp-session-id": "s"}, sse({"result": {}})),
                ({}, ""),
                ({}, sse({"result": {"content": []}})),
            ])

    def test_a_transient_failure_is_retried(self):
        calls = {"n": 0}

        def flaky(tool, args):
            calls["n"] += 1
            if calls["n"] == 1:
                raise mcp.McpUnavailable("upstream 503: None")
            return {"ok": True}

        with mock.patch.object(mcp, "_once", side_effect=flaky), \
             mock.patch.object(mcp.time, "sleep"):
            self.assertEqual(mcp.call("guide", {}, retries=3), {"ok": True})
        self.assertEqual(calls["n"], 2)


class TheQueryShape(unittest.TestCase):
    """Passing the entry id as `id`, or the params flat, returns a validation
    error rather than data. Verified against the live service."""

    def test_the_entry_id_and_params_are_nested_correctly(self):
        seen = {}
        with mock.patch.object(mcp, "call",
                               side_effect=lambda t, a: seen.update(tool=t, args=a)):
            mcp.query("equity_calendar_earnings", symbol="ORCL")
        self.assertEqual(seen["tool"], "do_query")
        self.assertEqual(seen["args"],
                         {"entry_id": "equity_calendar_earnings",
                          "params": {"symbol": "ORCL"}})


class TheSecondOpinion(unittest.TestCase):
    SESSION = dt.date(2026, 9, 10)

    def opinion(self, payload=None, error=None):
        if error is not None:
            ctx = mock.patch.object(mcp, "query",
                                    side_effect=mcp.McpUnavailable(error))
        else:
            ctx = mock.patch.object(mcp, "query", return_value=payload)
        with ctx:
            return crosscheck.second_opinion("ORCL", self.SESSION)

    def test_an_unreachable_service_is_unknown_never_no(self):
        """The failure mode that would make this whole check worthless."""
        verdict, detail = self.opinion(error="upstream 503: None")
        self.assertEqual(verdict, "unknown")
        self.assertIn("503", detail)

    def test_a_report_inside_the_window_is_yes(self):
        verdict, _ = self.opinion({"data": [{"symbol": "ORCL",
                                             "reportDate": "2026-09-10"}]})
        self.assertEqual(verdict, "yes")

    def test_a_report_on_the_next_session_is_still_in_the_window(self):
        verdict, _ = self.opinion({"rows": [{"date": "2026-09-11T20:00:00Z"}]})
        self.assertEqual(verdict, "yes")

    def test_a_report_outside_the_window_is_no(self):
        verdict, _ = self.opinion({"rows": [{"date": "2026-12-01"}]})
        self.assertEqual(verdict, "no")

    def test_dates_are_found_however_deeply_they_are_nested(self):
        verdict, _ = self.opinion({"a": {"b": [{"c": {"earnings_date": "2026-09-10"}}]}})
        self.assertEqual(verdict, "yes")


class TheIndex(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.ledger_path = root / "ledger.jsonl"
        lg = Ledger(self.ledger_path, b"t")
        # Two tickers across three sessions. One decision each would let a broken
        # cache pass unnoticed - the real ledger is 96 decisions over 12 names.
        for session in ("2026-09-10", "2026-09-11", "2026-09-14"):
            for ticker in ("ORCL", "NVDA"):
                lg.append("decision", {"ticker": ticker, "session": session,
                                       "action": "NO_HEDGE"})
        self.patches = [
            mock.patch.object(config, "LEDGER_PATH", self.ledger_path),
            mock.patch.object(config, "STATE", root),
            mock.patch.object(config, "secret", return_value=b"t"),
            mock.patch.object(mcp, "available", return_value=(True, "ok")),
        ]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in reversed(self.patches):
            p.stop()
        self.tmp.cleanup()

    def build(self, nasdaq, opinion):
        with mock.patch.object(crosscheck, "scheduled_in_window",
                               lambda t, s: nasdaq), \
             mock.patch.object(crosscheck, "second_opinion",
                               lambda t, s, cache=None: opinion):
            crosscheck.build()
        return crosscheck.load()

    def test_agreement_is_counted_when_both_say_yes(self):
        out = self.build("time-after-hours", ("yes", "reports 2026-09-10"))
        self.assertEqual(out["counts"]["agreed"], 6)
        self.assertEqual(out["counts"]["disagreed"], 0)

    def test_disagreement_is_published_not_hidden(self):
        out = self.build(None, ("yes", "reports 2026-09-10"))
        self.assertEqual(out["counts"]["disagreed"], 6)
        self.assertTrue(all(not r["agree"] for r in out["rows"]))

    def test_an_unknown_is_never_counted_as_agreement(self):
        out = self.build(None, ("unknown", "upstream 503: None"))
        c = out["counts"]
        self.assertEqual((c["agreed"], c["disagreed"], c["unknown"]), (0, 0, 6))
        # The counts exclude unknown rows, so they would stay at zero even if the
        # per-row flag lied. The flag is what a reader sees in the table.
        self.assertTrue(all(r["agree"] is False for r in out["rows"]),
                        "an unreachable second opinion was marked as agreement")

    def test_a_ticker_is_asked_once_however_many_sessions_it_appears_in(self):
        """96 decisions covered 12 tickers; the first cut made 96 calls."""
        calls = []
        with mock.patch.object(crosscheck, "scheduled_in_window",
                               lambda t, s: None), \
             mock.patch.object(mcp, "query",
                               side_effect=lambda e, **p: calls.append(p["symbol"])
                               or {"rows": []}):
            crosscheck.build()
        self.assertEqual(sorted(calls), ["NVDA", "ORCL"],
                         "a ticker was re-queried once per session")

    def test_it_stops_asking_once_the_service_is_clearly_down(self):
        calls = []

        def dead(entry, **params):
            calls.append(params["symbol"])
            raise mcp.McpUnavailable("upstream 503: None")

        with mock.patch.object(crosscheck, "scheduled_in_window",
                               lambda t, s: None), \
             mock.patch.object(crosscheck, "GIVE_UP_AFTER", 1), \
             mock.patch.object(mcp, "query", side_effect=dead):
            crosscheck.build()
        self.assertEqual(len(calls), 1, "kept querying a service known to be down")
        self.assertEqual(crosscheck.load()["counts"]["unknown"], 6)

    def test_the_service_status_is_recorded_beside_the_result(self):
        out = self.build(None, ("no", "0 dates returned"))
        self.assertIn("reachable", out["service"])
        self.assertEqual(out["source"], mcp.ENDPOINT)


if __name__ == "__main__":
    unittest.main()
