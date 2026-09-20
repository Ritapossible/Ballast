"""The Playbook's night selector, tested outside the Nautilus runtime.

`src/window.py` decides whether the strategy is short on any given bar. If it is
wrong every trade in the published backtest is wrong, and it is the only part of
the package that can be checked without the sandbox - so it is checked here,
beside everything else this project asserts.

The package itself is validated by the platform's own tool
(`python3 scripts/validate.py playbook/ballast-overnight-protection/`), which
these tests do not replace.
"""
from __future__ import annotations

import datetime as dt
import sys
import unittest
from pathlib import Path
from typing import ClassVar

PACKAGE = Path(__file__).resolve().parent.parent / "playbook" / \
    "ballast-overnight-protection"
sys.path.insert(0, str(PACKAGE / "src"))

import window  # noqa: E402

UTC = dt.timezone.utc


def at(year, month, day, hour, minute=0):
    return dt.datetime(year, month, day, hour, minute, tzinfo=UTC)


class TheOvernightWindow(unittest.TestCase):
    """20:00 UTC close to 13:30 UTC open, which is the EDT cash session."""

    def test_the_close_opens_the_window(self):
        self.assertTrue(window.inside_window(at(2026, 9, 10, 20)))

    def test_an_hour_before_the_close_is_not_in_it(self):
        self.assertFalse(window.inside_window(at(2026, 9, 10, 19)))

    def test_the_small_hours_are_in_it(self):
        self.assertTrue(window.inside_window(at(2026, 9, 11, 2)))

    def test_the_half_hour_before_the_bell_is_still_in_it(self):
        self.assertTrue(window.inside_window(at(2026, 9, 11, 13)))

    def test_after_the_bell_is_not(self):
        self.assertFalse(window.inside_window(at(2026, 9, 11, 14)))


class WhichNightABarBelongsTo(unittest.TestCase):
    def test_a_bar_after_the_close_belongs_to_that_day(self):
        self.assertEqual(window.protected_night(at(2026, 9, 10, 22)),
                         dt.date(2026, 9, 10))

    def test_a_bar_before_the_bell_belongs_to_the_day_before(self):
        self.assertEqual(window.protected_night(at(2026, 9, 11, 2)),
                         dt.date(2026, 9, 10))

    def test_a_weekend_bar_belongs_to_friday(self):
        """Monday 02:00 is Friday's night, not Sunday's - the window that
        actually carries the risk is the one that opened at Friday's close."""
        self.assertEqual(window.protected_night(at(2026, 9, 14, 2)),
                         dt.date(2026, 9, 11))
        self.assertEqual(window.protected_night(at(2026, 9, 13, 2)),
                         dt.date(2026, 9, 11))


class WhenItGoesShort(unittest.TestCase):
    EVENTS: ClassVar[dict] = {"ORCLUSDT": "2026-09-10"}

    def test_it_shorts_the_flagged_night(self):
        self.assertTrue(window.should_protect(
            "ORCLUSDT", at(2026, 9, 11, 2), self.EVENTS))

    def test_it_stays_flat_on_every_other_night(self):
        self.assertFalse(window.should_protect(
            "ORCLUSDT", at(2026, 9, 15, 2), self.EVENTS))

    def test_it_stays_flat_for_a_symbol_with_no_event(self):
        self.assertFalse(window.should_protect(
            "NVDAUSDT", at(2026, 9, 11, 2), self.EVENTS))

    def test_it_never_shorts_while_the_market_is_open(self):
        self.assertFalse(window.should_protect(
            "ORCLUSDT", at(2026, 9, 10, 17), self.EVENTS))

    def test_an_empty_mapping_protects_every_night(self):
        """The indiscriminate baseline the research rejects, kept reachable so
        the comparison can be run rather than asserted."""
        self.assertTrue(window.should_protect("ANY", at(2026, 9, 15, 2), {}))
        self.assertFalse(window.should_protect("ANY", at(2026, 9, 15, 17), {}))


class ThePackageMatchesTheProject(unittest.TestCase):
    def manifest(self) -> dict:
        import json
        import subprocess
        out = subprocess.run(
            [sys.executable, "-c",
             "import yaml,json,sys;print(json.dumps(yaml.safe_load(open(sys.argv[1]))))",
             str(PACKAGE / "manifest.yaml")],
            capture_output=True, text=True, check=True)
        return json.loads(out.stdout)

    def test_every_protected_night_names_a_symbol_the_package_trades(self):
        m = self.manifest()
        declared = set(m["trading_symbols"])
        flagged = set(m["strategy_config"]["event_dates"])
        self.assertEqual(flagged - declared, set(),
                         "an event date names a symbol the package cannot trade")

    def test_it_makes_no_alpha_claim(self):
        """Whitespace-normalised: the manifest wraps at 80 columns, so a raw
        substring match splits on whatever line break happens to fall inside
        the sentence."""
        m = self.manifest()
        text = " ".join(m["long_description"].lower().split())
        self.assertIn("not an alpha strategy", text)
        self.assertIn("makes no directional claim", text)
