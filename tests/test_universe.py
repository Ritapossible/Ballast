"""The rToken/perp pairing rule, and the ticker collision it has to survive.

Bitget lists stock perps and crypto perps in one USDT-futures namespace, and 34
tickers collide: rF is tokenized Ford while FUSDT is a crypto perp whose base coin
is F. Pairing on the bare ticker alone matched them, so `Book.from_tickers` would
have accepted Ford and hedged it with an unrelated crypto. Measured tracking on a
collided pair is R^2 ~= 0.00 against ~0.99 on a real one.

These fixtures are deliberately tiny and hand-written: the point is the rule, and
a fixture pulled from the live listing would stop testing it the day Bitget
reclassifies something.
"""
from __future__ import annotations

import unittest
from unittest import mock

from ballast import universe

SPOT = [
    {"symbol": "RTSLAUSDT", "baseCoin": "rTSLA", "status": "online"},
    {"symbol": "RFUSDT", "baseCoin": "rF", "status": "online"},       # Ford
    {"symbol": "RZZZUSDT", "baseCoin": "rZZZ", "status": "online"},   # no perp at all
    {"symbol": "RDEADUSDT", "baseCoin": "rDEAD", "status": "offline"},
    {"symbol": "RUNEUSDT", "baseCoin": "RUNE", "status": "online"},   # crypto, not an rToken
]
FUT_TICKERS = [{"symbol": s} for s in ("TSLAUSDT", "FUSDT", "RUNEUSDT")]
FUT_INSTRUMENTS = [
    {"symbol": "TSLAUSDT", "symbolType": "stock", "status": "online"},
    {"symbol": "FUSDT", "symbolType": "crypto", "status": "online"},   # the collision
    {"symbol": "RUNEUSDT", "symbolType": "crypto", "status": "online"},
]


def _patched():
    return (
        mock.patch.object(universe, "spot_symbols", return_value=SPOT),
        mock.patch.object(universe, "futures_tickers", return_value=FUT_TICKERS),
        mock.patch.object(universe, "instruments", return_value=FUT_INSTRUMENTS),
    )


class TestUniverse(unittest.TestCase):
    def setUp(self):
        for p in _patched():
            p.start()
            self.addCleanup(p.stop)

    def test_pairs_only_against_a_stock_perp(self):
        """rF must NOT pair with the crypto FUSDT, however well the names match."""
        self.assertEqual([p.ticker for p in universe.hedgeable_pairs()], ["TSLA"])

    def test_a_collided_name_is_reported_as_unprotectable(self):
        """Ford is not silently dropped - it lands in the half the site names."""
        self.assertIn("RFUSDT", universe.unhedgeable_rtokens())

    def test_names_with_no_perp_at_all_are_unhedgeable(self):
        self.assertIn("RZZZUSDT", universe.unhedgeable_rtokens())

    def test_offline_and_non_rtokens_are_in_neither_half(self):
        pairs, unpaired = universe.split_universe()
        seen = {p.spot for p in pairs} | {u.spot for u in unpaired}
        self.assertNotIn("RDEADUSDT", seen)
        self.assertNotIn("RUNEUSDT", seen)

    def test_a_perp_not_actually_trading_does_not_count(self):
        """Listed as a stock perp but absent from the tickers feed - no order can rest."""
        with mock.patch.object(universe, "futures_tickers", return_value=[]):
            self.assertEqual(universe.hedgeable_pairs(), [])

    def test_the_two_halves_partition_the_rtokens(self):
        pairs, unpaired = universe.split_universe()
        self.assertEqual(len(pairs) + len(unpaired), 3)          # TSLA, F, ZZZ
        self.assertFalse({p.ticker for p in pairs} & {u.ticker for u in unpaired})


if __name__ == "__main__":
    unittest.main()
