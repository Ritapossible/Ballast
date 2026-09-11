"""Red team against the enforcer.

Ballast's central claim is a negative capability:

    Every order Ballast can emit is opposite in sign to, and bounded in size by,
    a spot position already held. There is no code path to a directional trade.

These tests are the evidence for that sentence. Every hostile intent below must be
refused, and each asserts the SPECIFIC rule that refused it — a test that only
checks "rejected" would pass even if the wrong rule fired.
"""
from __future__ import annotations

import datetime as dt
import unittest

from ballast.enforcer import (Admitted, RULE_EXPIRED, RULE_NONPOSITIVE, RULE_NO_POSITION,
                              RULE_NOTIONAL, RULE_NOT_OPPOSITE, RULE_ORDER_COUNT,
                              RULE_RATIO, RULE_UNIVERSE, Enforcer, OrderIntent)
from ballast.executor import PaperExecutor
from ballast.mandate import MandateError, NightMandate, SignedMandate

SECRET = b"test-secret"
NOW = dt.datetime(2026, 9, 8, 21, 0, tzinfo=dt.timezone.utc)
EXPIRES = dt.datetime(2026, 9, 9, 13, 30, tzinfo=dt.timezone.utc)


def mandate(**kw) -> NightMandate:
    base = dict(issued_at=NOW, expires_at=EXPIRES,
                universe=("RTSLAUSDT", "RNVDAUSDT"),
                max_hedge_ratio=1.0, max_notional_usdt=5_000.0, max_orders=3)
    base.update(kw)
    return NightMandate(**base)


def enforcer(**kw) -> Enforcer:
    return Enforcer(SignedMandate.issue(mandate(**kw), SECRET), SECRET)


LONG_BOOK = {"RTSLAUSDT": 1_000.0, "RNVDAUSDT": 1_000.0}


class TestHostileIntents(unittest.TestCase):
    """Each of these is a way an attacker or a broken model might try to trade."""

    def test_naked_long_is_refused(self):
        """The headline claim: no position, no order — this is a directional bet."""
        v = enforcer().evaluate(
            OrderIntent("RTSLAUSDT", "TSLAUSDT", "buy", 500.0), {}, NOW)
        self.assertTrue(v.rejected)
        self.assertEqual(v.rule, RULE_NO_POSITION)

    def test_same_side_as_position_is_refused(self):
        """Buying the perp while long the spot doubles exposure — not a hedge."""
        v = enforcer().evaluate(
            OrderIntent("RTSLAUSDT", "TSLAUSDT", "buy", 500.0), LONG_BOOK, NOW)
        self.assertTrue(v.rejected)
        self.assertEqual(v.rule, RULE_NOT_OPPOSITE)

    def test_short_position_requires_the_opposite_hedge(self):
        v = enforcer().evaluate(
            OrderIntent("RTSLAUSDT", "TSLAUSDT", "sell", 500.0),
            {"RTSLAUSDT": -1_000.0}, NOW)
        self.assertEqual(v.rule, RULE_NOT_OPPOSITE)

    def test_over_hedging_is_refused_and_capped(self):
        """A hedge larger than the position is a net short — refused, with the cap."""
        v = enforcer().evaluate(
            OrderIntent("RTSLAUSDT", "TSLAUSDT", "sell", 1_500.0), LONG_BOOK, NOW)
        self.assertTrue(v.rejected)
        self.assertEqual(v.rule, RULE_RATIO)
        self.assertAlmostEqual(v.capped_notional, 1_000.0)

    def test_hedge_ratio_below_one_is_respected(self):
        v = enforcer(max_hedge_ratio=0.5).evaluate(
            OrderIntent("RTSLAUSDT", "TSLAUSDT", "sell", 800.0), LONG_BOOK, NOW)
        self.assertEqual(v.rule, RULE_RATIO)
        self.assertAlmostEqual(v.capped_notional, 500.0)

    def test_symbol_outside_universe_is_refused(self):
        v = enforcer().evaluate(
            OrderIntent("RAAPLUSDT", "AAPLUSDT", "sell", 100.0),
            {"RAAPLUSDT": 1_000.0}, NOW)
        self.assertEqual(v.rule, RULE_UNIVERSE)

    def test_expired_mandate_is_refused(self):
        after_open = EXPIRES + dt.timedelta(minutes=1)
        v = enforcer().evaluate(
            OrderIntent("RTSLAUSDT", "TSLAUSDT", "sell", 100.0), LONG_BOOK, after_open)
        self.assertEqual(v.rule, RULE_EXPIRED)

    def test_zero_and_negative_size_refused(self):
        for size in (0.0, -100.0):
            v = enforcer().evaluate(
                OrderIntent("RTSLAUSDT", "TSLAUSDT", "sell", size), LONG_BOOK, NOW)
            self.assertEqual(v.rule, RULE_NONPOSITIVE)

    def test_night_notional_budget_is_enforced(self):
        e = enforcer(max_notional_usdt=1_500.0)
        book = {"RTSLAUSDT": 1_000.0, "RNVDAUSDT": 1_000.0}
        first = OrderIntent("RTSLAUSDT", "TSLAUSDT", "sell", 1_000.0)
        self.assertTrue(e.evaluate(first, book, NOW).admitted)
        e.commit(first)
        second = OrderIntent("RNVDAUSDT", "NVDAUSDT", "sell", 1_000.0)
        v = e.evaluate(second, book, NOW)
        self.assertEqual(v.rule, RULE_NOTIONAL)

    def test_order_count_cap_is_enforced(self):
        e = enforcer(max_orders=1)
        intent = OrderIntent("RTSLAUSDT", "TSLAUSDT", "sell", 100.0)
        self.assertTrue(e.evaluate(intent, LONG_BOOK, NOW).admitted)
        e.commit(intent)
        self.assertEqual(e.evaluate(intent, LONG_BOOK, NOW).rule, RULE_ORDER_COUNT)

    def test_tampered_mandate_is_rejected_at_construction(self):
        """Widening the mandate after signing must not be usable."""
        signed = SignedMandate.issue(mandate(), SECRET)
        widened = SignedMandate(mandate=mandate(max_notional_usdt=1e9),
                                signature=signed.signature)
        with self.assertRaises(MandateError):
            Enforcer(widened, SECRET)

    def test_wrong_secret_is_rejected(self):
        signed = SignedMandate.issue(mandate(), SECRET)
        with self.assertRaises(MandateError):
            Enforcer(signed, b"attacker-secret")


class TestLegitimateHedge(unittest.TestCase):
    def test_exact_hedge_is_admitted(self):
        v = enforcer().evaluate(
            OrderIntent("RTSLAUSDT", "TSLAUSDT", "sell", 1_000.0), LONG_BOOK, NOW)
        self.assertTrue(v.admitted)
        self.assertIsNone(v.rule)

    def test_partial_hedge_is_admitted(self):
        v = enforcer().evaluate(
            OrderIntent("RTSLAUSDT", "TSLAUSDT", "sell", 400.0), LONG_BOOK, NOW)
        self.assertTrue(v.admitted)

    def test_unwinding_a_short_spot_is_admitted(self):
        v = enforcer().evaluate(
            OrderIntent("RTSLAUSDT", "TSLAUSDT", "buy", 500.0),
            {"RTSLAUSDT": -1_000.0}, NOW)
        self.assertTrue(v.admitted)


class TestMandateValidation(unittest.TestCase):
    def test_ratio_above_one_is_refused_at_issue(self):
        with self.assertRaises(MandateError):
            SignedMandate.issue(mandate(max_hedge_ratio=1.5), SECRET)

    def test_expiry_before_issue_is_refused(self):
        with self.assertRaises(MandateError):
            SignedMandate.issue(mandate(expires_at=NOW - dt.timedelta(hours=1)), SECRET)

    def test_empty_universe_is_refused(self):
        with self.assertRaises(MandateError):
            SignedMandate.issue(mandate(universe=()), SECRET)


if __name__ == "__main__":
    unittest.main()


class AdmissionIsUnforgeable(unittest.TestCase):
    """The executor used to take a symbol, a side and a size.

    Nothing but caller discipline in night.py stood between a bug and a naked
    directional order, and none of the red-team tests above could have caught it -
    they drive the enforcer, and the gap was downstream of it. These attack the
    seam itself.
    """

    def setUp(self):
        now = dt.datetime.now(dt.timezone.utc)
        m = NightMandate(issued_at=now, expires_at=now + dt.timedelta(hours=12),
                         universe=("RTSLAUSDT",), max_notional_usdt=10_000.0,
                         max_orders=5)
        self.now = now
        self.enforcer = Enforcer(SignedMandate.issue(m, b"k"), b"k")
        self.book = {"RTSLAUSDT": 1_000.0}
        self.hedge = OrderIntent("RTSLAUSDT", "TSLAUSDT", "sell", 900.0)
        self.executor = PaperExecutor()

    def test_an_admission_cannot_be_built_by_hand(self):
        with self.assertRaises(TypeError):
            Admitted(self.hedge)

    def test_a_guessed_token_does_not_work(self):
        for guess in (object(), "admitted", True, 1, None):
            with self.subTest(guess=guess), self.assertRaises(TypeError):
                Admitted(self.hedge, guess)

    def test_the_executor_refuses_a_raw_intent(self):
        """The bypass that used to be possible: call the executor directly."""
        with self.assertRaises(TypeError):
            self.executor.execute(self.hedge, 100.0, self.now)

    def test_the_executor_refuses_anything_that_is_not_an_admission(self):
        for impostor in (None, "ok", {"side": "buy"}, self.hedge):
            with self.subTest(impostor=type(impostor).__name__):
                with self.assertRaises(TypeError):
                    self.executor.execute(impostor, 100.0, self.now)

    def test_a_rejected_intent_yields_no_admission_to_pass(self):
        naked = OrderIntent("RTSLAUSDT", "TSLAUSDT", "buy", 500.0)   # directional
        verdict = self.enforcer.evaluate(naked, {}, self.now)
        self.assertTrue(verdict.rejected)
        self.assertIsNone(verdict.admission)

    def test_an_admitted_intent_fills_exactly_as_admitted(self):
        verdict = self.enforcer.evaluate(self.hedge, self.book, self.now)
        self.assertTrue(verdict.admitted)
        fill = self.executor.execute(verdict.admission, 100.0, self.now)
        self.assertEqual(fill.perp_symbol, "TSLAUSDT")
        self.assertEqual(fill.side, "sell")
        self.assertEqual(fill.notional_usdt, 900.0)

    def test_the_executor_cannot_be_asked_for_a_different_size(self):
        """There is no parameter for it. The fill comes from the admitted intent."""
        import inspect
        params = list(inspect.signature(self.executor.execute).parameters)
        self.assertEqual(params, ["admitted", "mark", "at"])
        for gone in ("notional_usdt", "side", "perp_symbol"):
            self.assertNotIn(gone, params)
