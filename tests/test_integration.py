"""End-to-end tests for the live path: night -> ledger -> morning -> site.

This path had no coverage at all, and it is where the audit found its three worst
defects: a settlement metric that marked ~90% of decisions wrong, production and
research disagreeing on how an overnight return is defined, and a single flaky
symbol aborting the whole run. Each of those is now pinned here.

Network is faked at the module boundary; nothing here touches an endpoint.
"""
from __future__ import annotations

import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from ballast import config, morning, night, report
from ballast.book import Book, Position
from ballast.ledger import Ledger
from ballast.market import MarketDataUnavailable
from ballast.sessions import UTC, close_utc, next_session, open_utc

SECRET = b"integration-secret"
SESSION = dt.date(2026, 9, 10)          # a Thursday
NOW = close_utc(SESSION) + dt.timedelta(hours=1)

TICKERS = ["ORCL", "TSLA", "SPY"]


def _series(spot: bool, drift: float = 0.0) -> dict[int, tuple[float, float]]:
    """Hourly (open, close) bars spanning several sessions, ending after the close."""
    bars, price = {}, 100.0
    start = close_utc(SESSION - dt.timedelta(days=30))
    for i in range(24 * 32):
        ts = int((start + dt.timedelta(hours=i)).timestamp() * 1000)
        opening = price
        price *= 1 + (drift if i % 24 == 0 else 0.0)
        bars[ts] = (opening, price)
    # the settling window: close of SESSION -> open of the next session
    bars[int(close_utc(SESSION).timestamp() * 1000)] = (100.0, 100.0)
    nxt = open_utc(next_session(SESSION)).replace(minute=0) + dt.timedelta(hours=1)
    bars[int(nxt.timestamp() * 1000)] = (92.0 if spot else 92.5, 92.0 if spot else 92.5)
    return bars


def fake_bars(symbol, market="spot", **kw):
    if symbol == "RFAILUSDT":
        raise MarketDataUnavailable("simulated outage")
    return _series(spot=market == "spot", drift=0.004 if symbol.startswith("R") else 0.004)


def build_book(path: Path, tickers=TICKERS) -> None:
    Book([Position(spot_symbol=f"R{t}USDT", perp_symbol=f"{t}USDT", ticker=t,
                   quantity=10.0, entry_price=100.0) for t in tickers]).save(path)


class LivePathCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.book_path = root / "book.json"
        self.ledger_path = root / "ledger.jsonl"
        build_book(self.book_path)
        self.patches = [
            mock.patch.object(config, "BOOK_PATH", self.book_path),
            mock.patch.object(config, "LEDGER_PATH", self.ledger_path),
            mock.patch.object(config, "STATE", root),
            mock.patch.object(config, "secret", return_value=SECRET),
            mock.patch.object(night, "market_bars", fake_bars),
            mock.patch.object(morning, "market_bars", fake_bars),
            mock.patch.object(night, "symbols_on",
                              lambda d: {"ORCL": "time-after-hours"}),
        ]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in reversed(self.patches):
            p.stop()
        self.tmp.cleanup()

    def ledger(self) -> Ledger:
        return Ledger(self.ledger_path, SECRET)

    def settle(self, **kw):
        return morning.run(**kw)

    def run_night(self, **kw):
        with mock.patch("ballast.night.dt", wraps=dt) as fake_dt:
            fake_dt.datetime.now.return_value = NOW
            fake_dt.timedelta = dt.timedelta
            fake_dt.date = dt.date
            return night.run(no_reader=True, **kw)


class TestNightRun(LivePathCase):
    def test_one_decision_per_position_and_a_summary(self):
        summary = self.run_night()
        ledger = self.ledger()
        self.assertEqual(ledger.verify(), len(TICKERS) + 2)      # mandate + decisions + summary
        self.assertEqual(len(ledger.records("decision")), len(TICKERS))
        self.assertEqual(summary["hedged"] + summary["declined"] + summary["errors"],
                         len(TICKERS))

    def test_the_calendar_hedges_only_the_reporting_name(self):
        self.run_night()
        by_ticker = {r["body"]["ticker"]: r["body"]
                     for r in self.ledger().records("decision")}
        self.assertEqual(by_ticker["ORCL"]["action"], "HEDGE")
        self.assertEqual(by_ticker["TSLA"]["action"], "NO_HEDGE")
        self.assertEqual(by_ticker["SPY"]["action"], "NO_HEDGE")

    def test_every_decision_records_its_hedge_leg(self):
        """Settlement must never have to guess the perp from the spot symbol."""
        self.run_night()
        for r in self.ledger().records("decision"):
            self.assertEqual(r["body"]["perp_symbol"], f"{r['body']['ticker']}USDT")

    def test_a_dead_symbol_does_not_abort_the_run(self):
        build_book(self.book_path, TICKERS + ["FAIL"])
        summary = self.run_night()
        self.assertEqual(summary["errors"], 1)
        self.assertEqual(len(self.ledger().records("decision")), len(TICKERS) + 1)
        failed = [r["body"] for r in self.ledger().records("decision")
                  if r["body"]["ticker"] == "FAIL"][0]
        self.assertIn("simulated outage", failed["error"])
        self.assertEqual(failed["action"], "NO_HEDGE")

    def test_the_mandate_cap_is_derived_from_the_book(self):
        """A fixed cap far above the book never binds and is not a control."""
        self.run_night()
        mandate = self.ledger().records("mandate")[0]["body"]
        gross = 10.0 * 100.0 * len(TICKERS)
        self.assertLess(mandate["max_notional_usdt"], gross * 1.2)
        self.assertEqual(mandate["max_orders"], len(TICKERS))

    def test_a_dry_run_consumes_the_same_budget(self):
        summary = self.run_night(dry_run=True)
        self.assertEqual(summary["usage"]["orders"], summary["hedged"])

    def test_rotating_the_signing_key_does_not_strand_the_chain(self):
        self.run_night()
        with mock.patch.object(config, "secret", return_value=b"a-new-key"):
            self.run_night()
            self.assertEqual(Ledger(self.ledger_path, b"a-new-key").verify(),
                             len(TICKERS) + 3)     # chain_start + mandate + n + summary
        self.assertTrue((Path(self.tmp.name) / "ledger.superseded.jsonl").exists())


class TestMorningSettlement(LivePathCase):
    def test_refusals_are_graded_by_outcome_not_by_cost(self):
        """The old metric marked every refusal wrong; the market fell here, so a
        refusal is genuinely wrong and a hedge genuinely right - both by P&L."""
        self.run_night()
        result = self.settle()
        rows = {r["ticker"]: r for r in result["sessions"][SESSION.isoformat()]["rows"]}
        self.assertTrue(rows["ORCL"]["correct"])        # hedged into an 800bp fall
        self.assertFalse(rows["TSLA"]["correct"])       # declined into the same fall
        self.assertGreater(rows["ORCL"]["value_added_bp"], 0)
        self.assertLess(rows["TSLA"]["value_added_bp"], 0)

    def test_a_refusal_on_a_rising_night_is_graded_correct(self):
        with mock.patch.object(morning, "market_bars",
                               lambda s, m="spot", **k: _rising(m)):
            self.run_night()
            rows = {r["ticker"]: r for r in
                    self.settle()["sessions"][SESSION.isoformat()]["rows"]}
        self.assertTrue(rows["TSLA"]["correct"])        # declined, and it rose
        self.assertFalse(rows["ORCL"]["correct"])       # hedged away the gain

    def test_settlement_is_idempotent(self):
        self.run_night()
        self.settle()
        again = self.settle(session=SESSION.isoformat())
        self.assertEqual(again["settled"], 0)
        self.assertEqual(len(self.ledger().records("settlement")), 1)

    def test_a_session_is_not_settled_while_any_row_is_ungradeable(self):
        """Partial settlement would strand the missing rows permanently."""
        self.run_night()
        real = fake_bars

        def patchy(symbol, market="spot", **kw):
            if symbol == "RSPYUSDT":
                return {}                    # no data for one leg yet
            return real(symbol, market, **kw)

        with mock.patch.object(morning, "market_bars", patchy):
            result = self.settle()
        self.assertEqual(result.get("settled", 0), 0)
        self.assertIn("SPY", result["deferred"][SESSION.isoformat()])
        self.assertEqual(self.ledger().records("settlement"), [])

    def test_settlement_never_reads_the_market_cache(self):
        """The cache never expires, so a cached bar would grade the wrong session."""
        self.run_night()
        calls = []

        def recording(symbol, market="spot", **kw):
            calls.append(kw)
            return fake_bars(symbol, market, **kw)

        with mock.patch.object(morning, "market_bars", recording):
            self.settle()
        self.assertTrue(calls, "settlement fetched no bars at all")
        self.assertTrue(all(kw.get("use_cache") is False for kw in calls), calls)
        self.assertTrue(all(kw.get("max_bars") == morning.SETTLE_BARS for kw in calls),
                        "settlement paged further back than the session it grades")

    def test_settlement_refuses_a_broken_chain(self):
        self.run_night()
        lines = self.ledger_path.read_text().splitlines()
        entry = json.loads(lines[1])
        entry["body"]["action"] = "NO_HEDGE" if entry["body"]["action"] == "HEDGE" else "HEDGE"
        lines[1] = json.dumps(entry)
        self.ledger_path.write_text("\n".join(lines) + "\n")
        with self.assertRaises(Exception):
            self.settle()


def _rising(market: str) -> dict[int, tuple[float, float]]:
    bars = _series(spot=market == "spot")
    nxt = open_utc(next_session(SESSION)).replace(minute=0) + dt.timedelta(hours=1)
    up = 106.0 if market == "spot" else 105.5
    bars[int(nxt.timestamp() * 1000)] = (up, up)
    return bars


class TestSiteReflectsTheLedger(LivePathCase):
    def test_the_pages_render_what_actually_happened(self):
        self.run_night()
        self.settle()
        out = Path(self.tmp.name) / "site"
        with mock.patch.object(report, "OUT_DIR", out):
            pages = {p.name: p.read_text() for p in report.build()}
        self.assertIn("ORCL", pages["tonight.html"])
        self.assertIn("chain verified", pages["tonight.html"])
        self.assertIn("correct", pages["settled.html"])
        self.assertNotIn("CHAIN BROKEN", pages["settled.html"])


if __name__ == "__main__":
    unittest.main()


class TestBitgetExport(LivePathCase):
    """The exported log must re-encode the ledger, never invent exchange data."""

    def test_only_executed_fills_become_orders(self):
        from ballast import export
        self.run_night()
        out = Path(self.tmp.name) / "orders.json"
        with mock.patch.object(config, "STATE", Path(self.tmp.name)):
            payload = json.loads(export.build(out).read_text())
        hedged = [r["body"] for r in self.ledger().records("decision")
                  if r["body"]["action"] == "HEDGE"]
        self.assertEqual(len(payload["data"]), len(hedged))

    def test_orders_carry_the_uta_field_names(self):
        from ballast import export
        self.run_night()
        out = Path(self.tmp.name) / "orders.json"
        order = json.loads(export.build(out).read_text())["data"][0]
        for field in ("orderId", "clientOid", "symbol", "productType", "marginCoin",
                      "side", "orderType", "price", "priceAvg", "size", "fee",
                      "feeCoin", "status", "cTime", "uTime"):
            self.assertIn(field, order)

    def test_every_row_is_marked_paper(self):
        from ballast import export
        self.run_night()
        out = Path(self.tmp.name) / "orders.json"
        payload = json.loads(export.build(out).read_text())
        self.assertIn("No order was sent to an exchange", payload["ballastNote"])
        for row in payload["data"]:
            self.assertIs(row["paper"], True)

    def test_export_is_deterministic(self):
        from ballast import export
        self.run_night()
        a = export.build(Path(self.tmp.name) / "a.json").read_text()
        b = export.build(Path(self.tmp.name) / "b.json").read_text()
        self.assertEqual(json.loads(a)["data"], json.loads(b)["data"])
