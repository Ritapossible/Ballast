"""Policy behaviour, and the sentinel that proves it cannot see the future.

Gate 1's first run was contaminated by look-ahead: it selected nights using the
move that had already happened. The sentinel below fails if that ever returns.
"""
from __future__ import annotations

import datetime as dt
import random
import unittest

from ballast.policy import (
    Action,
    EventType,
    Impact,
    NightRisk,
    PolicyConfig,
    decide,
    forecast_sigma_bp,
)

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
    """The site claims a sentinel test fails if a future night ever moves a past
    decision. For a while it could not fail. It built a polluted history, passed
    the ORIGINAL to decide() both times, and compared a function against itself on
    identical input; the one use of the polluted list was an assertion about its
    length, which is why nothing flagged it as dead.

    The property is also not a property of decide(), which is a pure function of
    whatever list it is handed - appending nights to that list is simply a later
    decision. Look-ahead can only enter where the history is SLICED, which is
    research/replay.py:

        prior = [v for d, v in hist[t] if d < session]

    That `<` is the guard. These tests exercise it.
    """

    @staticmethod
    def _prior(hist, session):
        """The replay's slice, reproduced exactly."""
        return [v for d, v in hist if d < session]

    def _history(self, seed=7):
        rng = random.Random(seed)
        start = dt.date(2026, 1, 5)
        return [(start + dt.timedelta(days=i), rng.gauss(0, 0.03)) for i in range(80)]

    def test_corrupting_the_future_cannot_move_a_past_decision(self):
        hist = self._history()
        session = hist[60][0]
        before = decide("X", "RXUSDT", self._prior(hist, session),
                        CALM_RISK, 17.5, CFG)

        rng = random.Random(99)
        corrupted = [(d, (v if d < session else rng.gauss(0, 0.9)))
                     for d, v in hist]
        after = decide("X", "RXUSDT", self._prior(corrupted, session),
                       CALM_RISK, 17.5, CFG)

        self.assertEqual(before.action, after.action)
        self.assertAlmostEqual(before.sigma_bp, after.sigma_bp, places=9)

    def test_the_sentinel_can_fail(self):
        """A test that cannot fail is worse than no test - it reads as coverage.

        The same corruption applied to nights the decision IS entitled to see must
        move it. If this passes silently, the test above proves nothing.
        """
        hist = self._history()
        session = hist[60][0]
        before = decide("X", "RXUSDT", self._prior(hist, session),
                        CALM_RISK, 17.5, CFG)

        rng = random.Random(99)
        corrupted = [(d, (rng.gauss(0, 0.9) if d < session else v))
                     for d, v in hist]
        after = decide("X", "RXUSDT", self._prior(corrupted, session),
                       CALM_RISK, 17.5, CFG)

        self.assertNotAlmostEqual(before.sigma_bp, after.sigma_bp, places=6)

    def test_an_inclusive_slice_would_be_caught(self):
        """Proof the guard is the `<`: widen it to `<=` and the answer moves."""
        hist = self._history()
        session = hist[60][0]
        rng = random.Random(99)
        corrupted = [(d, (v if d < session else rng.gauss(0, 0.9))) for d, v in hist]

        strict = decide("X", "RXUSDT", [v for d, v in corrupted if d < session],
                        CALM_RISK, 17.5, CFG)
        inclusive = decide("X", "RXUSDT", [v for d, v in corrupted if d <= session],
                           CALM_RISK, 17.5, CFG)
        self.assertNotAlmostEqual(strict.sigma_bp, inclusive.sigma_bp, places=6)

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
