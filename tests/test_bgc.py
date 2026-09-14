"""Agent Hub execution: what it must do, and what it must never do.

The dangerous failure here is not a crash - it is a silent substitution. If `bgc`
is missing or misconfigured and Ballast quietly simulates the fill while the ledger
still says "bgc-paper", the chain carries a claim about the venue that is false, and
nothing downstream can tell. Most of these tests exist for that one case.
"""
from __future__ import annotations

import datetime as dt
import json
import subprocess
import unittest
from unittest import mock

from ballast import bgc
from ballast.bgc import BgcExecutor, BgcUnavailable
from ballast.enforcer import Enforcer, OrderIntent
from ballast.mandate import NightMandate, SignedMandate

SECRET = b"test-secret"
NOW = dt.datetime(2026, 9, 8, 21, 0, tzinfo=dt.timezone.utc)
EXPIRES = dt.datetime(2026, 9, 9, 13, 30, tzinfo=dt.timezone.utc)
MARK = 100.0


def admitted():
    """A real admission from a real enforcer - never a hand-built stand-in."""
    m = NightMandate(issued_at=NOW, expires_at=EXPIRES, universe=("RTSLAUSDT",),
                     max_hedge_ratio=1.0, max_notional_usdt=5_000.0, max_orders=3)
    enforcer = Enforcer(SignedMandate.issue(m, SECRET), SECRET)
    verdict = enforcer.evaluate(
        OrderIntent("RTSLAUSDT", "TSLAUSDT", "sell", 1_000.0),
        {"RTSLAUSDT": 1_000.0}, NOW)
    assert verdict.admitted, verdict.rule
    return verdict.admission


def configured(**extra):
    env = {bgc.VENUE_ENV: "bgc", bgc.KEY_ENV: "demo-key"}
    env.update(extra)
    return mock.patch.dict("os.environ", env, clear=False)


def on_path(present: bool = True):
    return mock.patch.object(bgc.shutil, "which",
                             lambda _: "/usr/bin/bgc" if present else None)


def responds(stdout: str, returncode: int = 0):
    done = subprocess.CompletedProcess(args=["bgc"], returncode=returncode,
                                       stdout=stdout, stderr="")
    return mock.patch.object(bgc.subprocess, "run", return_value=done)


class Gating(unittest.TestCase):
    def test_off_unless_explicitly_requested(self):
        with mock.patch.dict("os.environ", {bgc.VENUE_ENV: ""}, clear=False):
            self.assertFalse(bgc.requested())
            ok, why = bgc.available()
            self.assertFalse(ok)
            self.assertIn(bgc.VENUE_ENV, why)

    def test_requires_the_binary(self):
        with configured(), on_path(False):
            ok, why = bgc.available()
            self.assertFalse(ok)
            self.assertIn("PATH", why)

    def test_requires_a_key(self):
        with configured(**{bgc.KEY_ENV: ""}), on_path():
            ok, why = bgc.available()
            self.assertFalse(ok)
            self.assertIn(bgc.KEY_ENV, why)

    def test_ready_when_all_three_hold(self):
        """Venue, binary, key. Companion credentials are reported, not required."""
        with configured(), on_path():
            ok, _ = bgc.available()
        self.assertTrue(ok)


class AuthorityBoundary(unittest.TestCase):
    def test_refuses_anything_that_is_not_an_admission(self):
        """The whole point of the interface: you cannot ask it for a trade."""
        for impostor in (None, "TSLAUSDT", 1_000.0, object()):
            with self.subTest(impostor=type(impostor).__name__), \
                 configured(), on_path(), self.assertRaises(TypeError):
                BgcExecutor().execute(impostor, MARK, NOW)

    def test_never_places_a_live_order(self):
        """--paper-trading is appended by this module and cannot be switched off."""
        with configured(), on_path(), responds(json.dumps({"avgPrice": 100.5})) as run:
            BgcExecutor().execute(admitted(), MARK, NOW)
        argv = run.call_args[0][0]
        self.assertIn("--paper-trading", argv)

    def test_the_key_never_reaches_the_command_line(self):
        with configured(), on_path(), responds(json.dumps({"avgPrice": 100.5})) as run:
            BgcExecutor().execute(admitted(), MARK, NOW)
        self.assertNotIn("demo-key", " ".join(run.call_args[0][0]))


class Fills(unittest.TestCase):
    def test_uses_the_venue_price_not_our_simulation(self):
        with configured(), on_path(), responds(json.dumps(
                {"avgPrice": 100.5, "notional": 1_000.0, "fee": 0.6})):
            fill = BgcExecutor().execute(admitted(), MARK, NOW)
        self.assertEqual(fill.price, 100.5)
        self.assertEqual(fill.fee_usdt, 0.6)
        self.assertEqual(fill.side, "sell")
        self.assertEqual(fill.perp_symbol, "TSLAUSDT")

    def test_slippage_is_measured_against_the_decided_mark(self):
        with configured(), on_path(), responds(json.dumps({"avgPrice": 100.5})):
            fill = BgcExecutor().execute(admitted(), MARK, NOW)
        self.assertAlmostEqual(fill.slippage_bp, 50.0, places=1)

    def test_still_marked_paper(self):
        with configured(), on_path(), responds(json.dumps({"avgPrice": 100.5})):
            self.assertTrue(BgcExecutor().execute(admitted(), MARK, NOW).paper)


class FailuresAreTypedNeverInvented(unittest.TestCase):
    """Every one of these must raise, so the caller can fall back and SAY so."""

    def test_nonzero_exit(self):
        done = subprocess.CompletedProcess(["bgc"], 1, stdout="", stderr="auth failed")
        with configured(), on_path(), \
             mock.patch.object(bgc.subprocess, "run", return_value=done), \
             self.assertRaises(BgcUnavailable) as caught:
            BgcExecutor().execute(admitted(), MARK, NOW)
        self.assertIn("auth failed", caught.exception.reason)

    def test_timeout(self):
        with configured(), on_path(), mock.patch.object(
                bgc.subprocess, "run",
                side_effect=subprocess.TimeoutExpired("bgc", bgc.TIMEOUT_S)), \
             self.assertRaises(BgcUnavailable) as caught:
            BgcExecutor().execute(admitted(), MARK, NOW)
        self.assertIn("timeout", caught.exception.reason)

    def test_unparseable_output(self):
        with configured(), on_path(), responds("not json at all"), \
             self.assertRaises(BgcUnavailable) as caught:
            BgcExecutor().execute(admitted(), MARK, NOW)
        self.assertIn("unparseable", caught.exception.reason)


class AfterTheOrderMayExist(unittest.TestCase):
    """placeOrder acknowledges; it does not report a fill.

    Once the command has returned 0 the venue may be holding the order, so nothing
    downstream may raise. A caller that fell back here would simulate a fill for an
    order that already exists and the ledger would show one hedge where two were
    placed. Missing fields are recorded as missing instead.
    """

    def test_no_fill_price_falls_back_to_the_mark_and_says_so(self):
        with configured(), on_path(), responds(json.dumps(
                {"data": {"orderId": "994431"}})):
            ex = BgcExecutor()
            fill = ex.execute(admitted(), MARK, NOW)
        self.assertEqual(fill.price, MARK)
        self.assertIn("observed mark", ex.last_order["price_source"])
        self.assertEqual(ex.last_order["order_id"], "994431")

    def test_a_venue_price_is_labelled_as_the_venue(self):
        with configured(), on_path(), responds(json.dumps(
                {"data": {"orderId": "1", "avgPrice": 212.4}})):
            ex = BgcExecutor()
            fill = ex.execute(admitted(), MARK, NOW)
        self.assertEqual(fill.price, 212.4)
        self.assertEqual(ex.last_order["price_source"], "venue")

    def test_unusable_price_does_not_raise(self):
        for bad in (0, "abc", None, {"nested": 1}):
            with self.subTest(bad=bad), configured(), on_path(), \
                 responds(json.dumps({"data": {"orderId": "1", "avgPrice": bad}})):
                fill = BgcExecutor().execute(admitted(), MARK, NOW)
            self.assertEqual(fill.price, MARK)

    def test_notional_is_converted_to_base_coin_quantity(self):
        """qty is base coin for USDT futures; Ballast sizes in USDT."""
        with configured(), on_path(), responds(json.dumps(
                {"data": {"orderId": "1"}})) as run:
            ex = BgcExecutor()
            ex.execute(admitted(), MARK, NOW)     # 1,000 USDT at a mark of 100
        argv = run.call_args[0][0]
        self.assertEqual(argv[argv.index("--qty") + 1], "10")
        self.assertEqual(ex.last_order["qty"], 10.0)

    def test_the_verified_argv_is_what_gets_sent(self):
        with configured(), on_path(), responds(json.dumps(
                {"data": {"orderId": "1"}})) as run:
            BgcExecutor().execute(admitted(), MARK, NOW)
        argv = run.call_args[0][0]
        for flag, value in (("--category", "USDT-FUTURES"), ("--symbol", "TSLAUSDT"),
                            ("--side", "sell"), ("--orderType", "market")):
            self.assertEqual(argv[argv.index(flag) + 1], value)
        self.assertEqual(argv[1:4], ["order", "--action", "place"])
        self.assertNotIn("--json", argv)      # bgc has no such flag


class StillTypedBeforeTheOrderExists(unittest.TestCase):
    def test_unconfigured_raises_rather_than_simulating(self):
        """The substitution this module exists to prevent."""
        with mock.patch.dict("os.environ", {bgc.VENUE_ENV: ""}, clear=False), \
             self.assertRaises(BgcUnavailable):
            BgcExecutor().execute(admitted(), MARK, NOW)


if __name__ == "__main__":
    unittest.main()


class CompanionCredentials(unittest.TestCase):
    """Bitget signs with a triplet. Missing halves are reported, never fatal."""

    def test_reported_when_unset(self):
        with configured(), on_path():
            ok, why = bgc.available()
        self.assertTrue(ok, "a missing companion must not block the venue")
        for name in bgc.COMPANION_ENV:
            self.assertIn(name, why)

    def test_clean_when_all_present(self):
        with configured(**dict.fromkeys(bgc.COMPANION_ENV, "x")), on_path():
            self.assertEqual(bgc.available(), (True, "ready"))


class FailuresAreReadable(unittest.TestCase):
    """bgc prints a pretty JSON error envelope. The reason has to survive it."""

    ENVELOPE = json.dumps({
        "ok": False,
        "error": {"type": "ConfigError", "message": "Partial API credentials detected.",
                  "suggestion": "Provide apiKey, secretKey and passphrase together."},
    }, indent=2)

    def test_the_message_not_the_last_brace(self):
        """Reading the last line of pretty JSON reported '}' and explained nothing."""
        with configured(), on_path(), responds(self.ENVELOPE, returncode=1), \
             self.assertRaises(BgcUnavailable) as caught:
            BgcExecutor().execute(admitted(), MARK, NOW)
        self.assertIn("Partial API credentials", caught.exception.reason)
        self.assertNotEqual(caught.exception.reason.strip()[-1], "}")

    def test_a_refusal_on_a_zero_exit_still_raises(self):
        with configured(), on_path(), responds(self.ENVELOPE, returncode=0), \
             self.assertRaises(BgcUnavailable) as caught:
            BgcExecutor().execute(admitted(), MARK, NOW)
        self.assertIn("Partial API credentials", caught.exception.reason)
