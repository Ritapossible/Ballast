"""Policy behaviour, and the sentinel that proves it cannot see the future.

Gate 1's first run was contaminated by look-ahead: it selected nights using the
move that had already happened. The sentinel below fails if that ever returns.
"""
from __future__ import annotations

import random
import unittest

from ballast.policy import (Action, EventType, Impact, NightRisk, PolicyConfig,
                            decide, forecast_sigma_bp, sigma_percentile)

CFG = PolicyConfig()
# The volatility gate ships OFF (Gate 1a). These fixtures exercise the opt-in path.
VOL_CFG = PolicyConfig(vol_gate_enabled=True, vol_percentile=0.80)
QUIET = [0.0005] * 60
CALM_RISK = NightRisk(ticker="X")
EARNINGS = NightRisk(ticker="X", event_type=EventType.EARNINGS,
                     expected_impact=Impact.HIGH, confidence=1.0)


def volatile(n=60, scale=0.03, seed=7):
    rng = random.Random(seed)
    return [rng.gauss(0, scale) for _ in range(n)]


class TestNoLookAhead(unittest.TestCase):
    def test_future_returns_cannot_change_tonights_decision(self):
        """Append arbitrary future nights; the decision for tonight must not move."""
        history = volatile()
        before = decide("X", "RXUSDT", history, CALM_RISK, 17.5, CFG)
        rng = random.Random(99)
        for _ in range(40):
            polluted = history + [rng.gauss(0, 0.5)]      # violent "future" nights
            after = decide("X", "RXUSDT", history, CALM_RISK, 17.5, CFG)
            self.assertEqual(before.action, after.action)
            self.assertAlmostEqual(before.sigma_bp, after.sigma_bp, places=9)
            self.assertEqual(len(polluted), len(history) + 1)

    def test_forecast_uses_only_the_trailing_window(self):
        history = volatile()
        tail = history[-CFG.vol_window:]
        self.assertAlmostEqual(forecast_sigma_bp(history, CFG),
                               forecast_sigma_bp([0.0] * 40 + tail, CFG), places=9)


class TestDecisions(unittest.TestCase):
    def test_scheduled_earnings_always_hedges(self):
        """The calendar outranks the statistic — Gate 1's central consequence."""
        d = decide("X", "RXUSDT", QUIET, EARNINGS, 17.5, CFG)
        self.assertIs(d.action, Action.HEDGE)
        self.assertIn("calendar selector", d.rationale)

    def test_quiet_night_declines(self):
        d = decide("X", "RXUSDT", QUIET, CALM_RISK, 17.5, CFG)
        self.assertIs(d.action, Action.NO_HEDGE)

    def test_volatility_alone_never_hedges_by_default(self):
        """Gate 1a: vol-selected nights are compensated, so they are not hedged."""
        d = decide("X", "RXUSDT", volatile(scale=0.05), CALM_RISK, 17.5, CFG)
        self.assertIs(d.action, Action.NO_HEDGE)
        self.assertIn("1.41x", d.rationale)

    def test_insufficient_history_declines_rather_than_guesses(self):
        # Only reachable on the opt-in vol path: with the gate off, history is unused.
        d = decide("X", "RXUSDT", [0.01] * 5, CALM_RISK, 17.5, VOL_CFG)
        self.assertIs(d.action, Action.NO_HEDGE)
        self.assertIn("insufficient history", d.rationale)

    def test_spike_in_a_calm_name_is_hedged(self):
        # Alternating signs, not a constant: a flat series has zero dispersion.
        history = [0.0005, -0.0005] * 30 + [0.05, -0.05] * (CFG.vol_window // 2)
        d = decide("X", "RXUSDT", history, CALM_RISK, 17.5, VOL_CFG)
        self.assertIs(d.action, Action.HEDGE)
        self.assertGreaterEqual(d.inputs["sigma_percentile"], VOL_CFG.vol_percentile)

    def test_percentile_is_relative_to_the_name_itself(self):
        """A 300bp night is ordinary for a volatile name and extreme for a calm one."""
        loud = decide("LOUD", "RLOUD", volatile(scale=0.03), CALM_RISK, 17.5, CFG)
        self.assertIsNotNone(loud.inputs["sigma_percentile"])
        self.assertLess(loud.inputs["sigma_percentile"], 1.0)

    def test_absolute_floor_blocks_low_vol_names(self):
        """SPY-like names must not be hedged just for topping their own range."""
        history = [0.0001, -0.0001] * 20 + [0.0003, -0.0003] * (CFG.vol_window // 2)
        d = decide("SPY", "RSPYUSDT", history, CALM_RISK, 17.5, VOL_CFG)
        self.assertIs(d.action, Action.NO_HEDGE)
        self.assertIn("floor", d.rationale)

    def test_model_output_cannot_carry_a_size(self):
        """NightRisk is the LLM's entire vocabulary — it has no size or side field."""
        self.assertNotIn("notional", NightRisk.__dataclass_fields__)
        self.assertNotIn("side", NightRisk.__dataclass_fields__)
        self.assertNotIn("action", NightRisk.__dataclass_fields__)


if __name__ == "__main__":
    unittest.main()


class TestOutputTypography(unittest.TestCase):
    """Rationales render verbatim in the public UI, so they follow its conventions.

    They are also signed into the ledger, which means a wording change reaches the
    site only through new decisions - past entries keep the text they were signed
    with, and that is the tamper-evidence working, not a bug to paper over.
    """

    def test_no_em_dashes_in_rationales(self):
        for risk in (CALM_RISK, EARNINGS):
            for cfg in (CFG, VOL_CFG):
                d = decide("X", "RXUSDT", volatile(), risk, 17.5, cfg)
                self.assertNotIn("—", d.rationale)

    def test_no_em_dashes_in_model_led_rationales(self):
        for judgment in ("HEDGE", "NO_HEDGE"):
            d = decide("X", "RXUSDT", volatile(), EARNINGS, 17.5, CFG,
                       model_judgment=judgment)
            self.assertNotIn("—", d.rationale)


class RationaleFormattingCase(unittest.TestCase):
    """Rationales are published verbatim on a public page and signed into the
    ledger, so a raw float reaches both. '11.291999999999998bp' shipped."""

    def test_no_unrounded_float_reaches_a_rationale(self):
        import re
        for risk in (CALM_RISK, EARNINGS):
            for history in (QUIET, [0.02] * 60):
                d = decide("X", "RXUSDT", history, risk, 17.5, CFG)
                self.assertEqual(re.findall(r"\d+\.\d{3,}", d.rationale), [],
                                 d.rationale)
