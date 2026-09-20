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


class WhatTheServerRejectsButTheLocalValidatorAllows(unittest.TestCase):
    """The platform ships `scripts/validate.py`, and it is weaker than the
    control plane behind it.

    The first upload passed local validation and was rejected with four errors:
    a stray `.pyc` inside `src/`, a `user_config_schema` type outside the
    permitted set, a missing `margin_budget`, and a `long_description` over the
    word cap. Each cost a round trip to a third-party API to discover. They are
    checked here so the next one is caught before the call is made.
    """

    ALLOWED_TYPES: ClassVar[set] = {"array", "boolean", "integer", "number", "string"}

    def manifest(self) -> dict:
        import json
        import subprocess
        out = subprocess.run(
            [sys.executable, "-c",
             "import yaml,json,sys;print(json.dumps(yaml.safe_load(open(sys.argv[1]))))",
             str(PACKAGE / "manifest.yaml")],
            capture_output=True, text=True, check=True)
        return json.loads(out.stdout)

    def test_no_compiled_bytecode_ships_in_the_package(self):
        """`src/**` is uploaded verbatim; a .pyc is rejected as a local-only
        path and as non-UTF-8 text. Running these very tests creates one."""
        stray = [str(p.relative_to(PACKAGE)) for p in PACKAGE.rglob("*")
                 if p.suffix == ".pyc" or p.name == "__pycache__"]
        self.assertEqual(stray, [], f"these would be uploaded: {stray}")

    def test_every_declared_user_setting_has_a_permitted_type(self):
        for field, spec in (self.manifest().get("user_config_schema") or {}).items():
            self.assertIn(spec.get("type"), self.ALLOWED_TYPES,
                          f"{field} declares a type the platform refuses")

    def test_margin_budget_is_declared_and_positive(self):
        """Return % is net_pnl / margin_budget, so the platform cannot compute
        a return at all without it."""
        budget = (self.manifest().get("strategy_config") or {}).get("margin_budget")
        self.assertIsNotNone(budget, "margin_budget is required")
        self.assertGreater(float(budget), 0)

    def test_the_long_description_is_within_the_word_cap(self):
        words = len(self.manifest()["long_description"].split())
        self.assertGreaterEqual(words, 300)
        self.assertLessEqual(words, 400, f"{words} words; the cap is 400")


class EverySdkCallExistsInTheReference(unittest.TestCase):
    """Two invented calls cost a sandbox run each to discover.

    `runtime.is_backtest` and `backtest.write_report` both read like real API -
    the first is how most engines spell it, the second is what the output
    guidance implies. Neither exists. The platform only says so when it runs the
    package, so each guess cost an upload, a dispatch and a poll to disprove.

    The reference ships with the skill. When it is installed, every
    `getagent.*` attribute this package touches is checked against it. Parsed
    with AST rather than grepped, because the module docstring above names both
    invented calls on purpose and a text search would happily approve them.
    """

    SKILL = Path.home() / ".claude" / "skills" / "getagent" / "references"
    MODULES: ClassVar[set] = {"runtime", "backtest", "data", "trade", "llm"}

    def sdk_calls(self, source: Path) -> set:
        import ast
        found = set()
        for node in ast.walk(ast.parse(source.read_text())):
            if not isinstance(node, ast.Attribute):
                continue
            parts = []
            cur = node
            while isinstance(cur, ast.Attribute):
                parts.append(cur.attr)
                cur = cur.value
            if isinstance(cur, ast.Name) and cur.id in self.MODULES:
                parts.append(cur.id)
                found.add(".".join(reversed(parts)))
        return found

    def test_no_call_is_invented(self):
        if not self.SKILL.is_dir():
            self.skipTest("getagent skill not installed in this environment")
        corpus = "\n".join(
            p.read_text(errors="replace") for p in self.SKILL.rglob("*.md"))
        demo = (self.SKILL.parent / "examples").rglob("*.py")
        corpus += "\n".join(p.read_text(errors="replace") for p in demo)

        missing = sorted(
            call for call in self.sdk_calls(PACKAGE / "src" / "main.py")
            if call not in corpus)
        self.assertEqual(missing, [],
                         f"not in the reference, so the platform will reject "
                         f"them at run time: {missing}")


class MalformedBarsAreRepairedNotHidden(unittest.TestCase):
    """Nautilus refuses a bar whose high is below its open, and the whole replay
    dies on the first one. Thin RWA perpetuals do produce such bars upstream."""

    def setUp(self):
        # pandas is a dev/CI tool here, like ruff and mypy. Ballast itself has no
        # third-party runtime dependency and this must not quietly add one, so
        # the guard skips where pandas is absent and runs in the Playbook
        # workflow, which installs it alongside the platform validator.
        try:
            import pandas  # noqa: F401
        except ImportError:
            self.skipTest("pandas not installed; runs in the Playbook workflow")

    def frame(self, rows):
        import pandas as pd
        return pd.DataFrame(rows, columns=["open", "high", "low", "close", "volume"])

    def repair(self, rows):
        # main.py imports getagent, which only exists in the sandbox, so the
        # helper is read out and compiled rather than imported.
        src = (PACKAGE / "src" / "main.py").read_text()
        start = src.index("def _repair(")
        end = src.index("\ndef ", start + 1)
        namespace: dict = {}
        exec(compile(src[start:end], "_repair", "exec"), namespace)  # noqa: S102
        return namespace["_repair"](self.frame(rows))

    def test_a_high_below_the_open_is_lifted_to_the_open(self):
        frame, broken = self.repair([[10.0, 9.0, 8.0, 9.5, 1.0]])
        self.assertEqual(broken, 1)
        self.assertEqual(frame["high"].iloc[0], 10.0)

    def test_a_low_above_the_close_is_dropped_to_the_close(self):
        frame, broken = self.repair([[10.0, 11.0, 10.5, 9.0, 1.0]])
        self.assertEqual(broken, 1)
        self.assertEqual(frame["low"].iloc[0], 9.0)

    def test_a_sound_bar_is_left_alone_and_not_counted(self):
        frame, broken = self.repair([[10.0, 11.0, 9.0, 10.5, 1.0]])
        self.assertEqual(broken, 0)
        self.assertEqual((frame["high"].iloc[0], frame["low"].iloc[0]), (11.0, 9.0))

    def test_nothing_is_invented_beyond_the_bars_own_prices(self):
        """The repaired extremes come from the bar's own four prices, so a
        repair can never widen a bar past what it actually traded."""
        frame, _ = self.repair([[10.0, 9.0, 8.0, 9.5, 1.0]])
        self.assertLessEqual(frame["high"].iloc[0], 10.0)
        self.assertGreaterEqual(frame["low"].iloc[0], 8.0)
