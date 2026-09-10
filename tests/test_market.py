"""The market client has to work on a machine that has never run it before.

Every scheduled run is a fresh checkout: .cache/ is gitignored, so the cache
directory and its parent are both absent. Mocking market_bars - which the
integration tests do, correctly - hides that, so this exercises the client itself.
"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from ballast import market

ROWS = [["1757376000000", "100", "101", "99", "100.5", "1", "100"]]


class CacheDirectoryCase(unittest.TestCase):
    def test_caching_creates_a_missing_parent_directory(self):
        """mkdir(exist_ok=True) without parents=True raised FileNotFoundError.

        It never fired locally, where .cache/ already existed from research runs,
        and broke every scheduled settlement on the runner.
        """
        with tempfile.TemporaryDirectory() as d:
            cache = Path(d) / "absent" / "market"      # neither level exists
            with mock.patch.object(market, "CACHE", cache), \
                 mock.patch.object(market, "_get", side_effect=[{"data": ROWS}, {"data": []}]):
                rows = market.candles("RTSLAUSDT", "spot")
        self.assertEqual(rows, ROWS)

    def test_a_second_call_is_served_from_the_cache(self):
        with tempfile.TemporaryDirectory() as d:
            cache = Path(d) / "absent" / "market"
            with mock.patch.object(market, "CACHE", cache), \
                 mock.patch.object(market, "_get", side_effect=[{"data": ROWS}, {"data": []}]):
                market.candles("RTSLAUSDT", "spot")
                # _get is exhausted; a second network call would raise StopIteration.
                self.assertEqual(market.candles("RTSLAUSDT", "spot"), ROWS)
            self.assertEqual(json.loads((cache / "RTSLAUSDT_spot_1h.json").read_text()), ROWS)

    def test_use_cache_false_neither_reads_nor_writes(self):
        with tempfile.TemporaryDirectory() as d:
            cache = Path(d) / "market"
            cache.mkdir(parents=True)
            (cache / "RTSLAUSDT_spot_1h.json").write_text(json.dumps([["1", "1", "1", "1", "1", "1", "1"]]))
            with mock.patch.object(market, "CACHE", cache), \
                 mock.patch.object(market, "_get", side_effect=[{"data": ROWS}, {"data": []}]):
                rows = market.candles("RTSLAUSDT", "spot", use_cache=False)
            self.assertEqual(rows, ROWS)                      # the stale file was ignored
            self.assertEqual(len(list(cache.iterdir())), 1)   # and not overwritten


if __name__ == "__main__":
    unittest.main()
