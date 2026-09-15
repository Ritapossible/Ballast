"""The coverage index: what it publishes, and what it refuses to publish.

The lookup on the site is only as honest as this file. Two properties carry that
weight: a pair with too little history is published as HAVING NO FIT rather than
as a confident beta from six nights, and one leg failing must cost that name its
fit and no other name anything at all.
"""
from __future__ import annotations

import json
import math
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from ballast import coverage
from ballast.market import MarketDataUnavailable
from ballast.universe import Pair, Unpaired

HOUR = 3_600_000


def _series(nights: int, *, scale: float = 1.0, seed: float = 0.013):
    """Hourly (open, close) bars spanning `nights` days, moving deterministically."""
    bars, price = {}, 100.0
    start = 1_756_000_000_000 - (1_756_000_000_000 % HOUR)
    for h in range(nights * 24 + 24):
        # A per-hour wobble, so the two legs correlate but are not identical.
        step = math.sin(h * seed) * 0.004 * scale
        nxt = price * math.exp(step)
        bars[start + h * HOUR] = (price, nxt)
        price = nxt
    return bars


class TestCoverage(unittest.TestCase):
    def _fit(self, spot_bars, perp_bars):
        def fake(symbol, market="spot", **kw):
            if market == "spot":
                return spot_bars
            return perp_bars
        with mock.patch.object(coverage, "bars", side_effect=fake):
            return coverage._fit(Pair("TSLA", "RTSLAUSDT", "TSLAUSDT"))

    def test_a_tracked_pair_publishes_a_fit(self):
        row = self._fit(_series(60), _series(60))
        self.assertTrue(row["fit"])
        self.assertAlmostEqual(row["beta"], 1.0, places=1)
        self.assertGreater(row["r2"], 0.9)
        self.assertGreaterEqual(row["nights"], coverage.MIN_NIGHTS)

    def test_too_little_history_publishes_no_fit(self):
        """Six nights is enough to compute a beta and not enough to mean one."""
        row = self._fit(_series(6), _series(6))
        self.assertIsNone(row["fit"])
        self.assertIn("too few", row["why"])
        self.assertNotIn("beta", row)

    def test_a_failing_leg_is_named_not_raised(self):
        with mock.patch.object(coverage, "bars", side_effect=MarketDataUnavailable("x")):
            row = coverage._fit(Pair("TSLA", "RTSLAUSDT", "TSLAUSDT"))
        self.assertIsNone(row["fit"])
        self.assertEqual(row["why"], "MarketDataUnavailable")
        self.assertEqual(row["nights"], 0)

    def test_one_bad_name_does_not_cost_the_others_their_row(self):
        pairs = [Pair("AAA", "RAAAUSDT", "AAAUSDT"), Pair("BBB", "RBBBUSDT", "BBBUSDT")]

        def fake(symbol, market="spot", **kw):
            if symbol.startswith(("RBBB", "BBB")):
                raise MarketDataUnavailable(symbol)
            return _series(60)

        with tempfile.TemporaryDirectory() as d, \
             mock.patch.object(coverage, "split_universe",
                               return_value=(pairs, [Unpaired("ZZZ", "RZZZUSDT")])), \
             mock.patch.object(coverage, "bars", side_effect=fake):
            payload = json.loads(coverage.build(Path(d) / "c.json").read_text())

        rows = {r["ticker"]: r for r in payload["covered"]}
        self.assertTrue(rows["AAA"]["fit"])
        self.assertIsNone(rows["BBB"]["fit"])
        self.assertEqual(payload["counts"], {"rtokens": 3, "covered": 2,
                                             "uncovered": 1, "fitted": 1})
        self.assertEqual(payload["uncovered"], ["ZZZ"])

    def test_the_bounded_pull_never_writes_the_shared_candle_cache(self):
        """market.candles keys its cache by symbol alone, so a truncated pull saved
        under that key would be served to the nightly decision run."""
        seen = []

        def fake(symbol, market="spot", **kw):
            seen.append(kw)
            return _series(60)

        with mock.patch.object(coverage, "bars", side_effect=fake):
            coverage._fit(Pair("TSLA", "RTSLAUSDT", "TSLAUSDT"))
        self.assertTrue(seen)
        for kw in seen:
            self.assertIs(kw.get("use_cache"), False)
            self.assertEqual(kw.get("max_bars"), coverage.WINDOW_BARS)


if __name__ == "__main__":
    unittest.main()
