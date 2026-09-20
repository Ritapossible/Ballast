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

# Importing window.py writes a .pyc into the package, which the upload rejects
# as a local-only path - and which the guard below would then correctly find,
# failing verify.py for a file these very tests created. Stop it being written
# rather than clean it up afterwards and hope the ordering holds.
sys.dont_write_bytecode = True
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



def _scalar(raw: str) -> object:
    """The scalar forms this manifest uses, and no others."""
    if raw.startswith(('"', "'")) and raw.endswith(raw[0]) and len(raw) > 1:
        return raw[1:-1]
    if raw in ("true", "false"):
        return raw == "true"
    if raw in ("null", "~", ""):
        return None
    try:
        return int(raw)
    except ValueError:
        pass
    try:
        return float(raw)
    except ValueError:
        return raw


def _strip_comment(line: str) -> str:
    if line.lstrip().startswith("#"):
        return ""
    value = line.split(": ", 1)[-1].lstrip()
    if value.startswith(('"', "'")):
        return line
    return line.split(" #", 1)[0]


def load_yaml(path: Path) -> dict:
    """A reader for the subset of YAML `manifest.yaml` is written in.

    The tests used to shell out to PyYAML. That made `python3 verify.py` - the
    command the site gives a judge, documented as needing nothing but the
    standard library - fail with five errors on any clone without PyYAML
    installed, and it had been failing in CI for the same reason.

    Anything outside the subset raises rather than being guessed at -
    `backtest.yaml`, which nests mappings inside sequences, is refused rather
    than half-read - and `TheReaderAgreesWithTheRealParser` below holds it to
    PyYAML's answer wherever PyYAML is available.
    """
    lines = [_strip_comment(raw.rstrip()) for raw in path.read_text().splitlines()]
    for n, raw in enumerate(lines, 1):
        if "\t" in raw:
            raise ValueError(f"{path.name}:{n}: tab indentation")
        if raw.strip() in ("---", "..."):
            raise ValueError(f"{path.name}:{n}: multiple documents")
        if raw.lstrip()[:1] in ("&", "*"):
            raise ValueError(f"{path.name}:{n}: anchors are not supported")

    def indent(i: int) -> int:
        return len(lines[i]) - len(lines[i].lstrip())

    def block(start: int, end: int, col: int) -> object:
        i, seq, mapping = start, [], {}
        while i < end:
            if not lines[i].strip():
                i += 1
                continue
            if indent(i) != col:
                raise ValueError(f"{path.name}:{i + 1}: unexpected indentation")
            line = lines[i].strip()
            if line.startswith("- "):
                seq.append(_scalar(line[2:].strip()))
                i += 1
                continue
            if ":" not in line:
                raise ValueError(f"{path.name}:{i + 1}: not a mapping entry")
            key, _, rest = line.partition(":")
            rest = rest.strip()
            j = i + 1
            while j < end and (not lines[j].strip() or indent(j) > col):
                j += 1
            if rest in ("|", "|-", "|+"):
                body = lines[i + 1 : j]
                pad = min((len(b) - len(b.lstrip()) for b in body if b.strip()),
                          default=0)
                text = "\n".join(b[pad:] for b in body).rstrip("\n")
                mapping[key.strip()] = text + ("" if rest == "|-" else "\n")
            elif rest.startswith(("{", "[", ">", "&", "*")):
                raise ValueError(f"{path.name}:{i + 1}: {rest[0]!r} is not supported")
            elif rest:
                mapping[key.strip()] = _scalar(rest)
            elif j > i + 1:
                inner = next(k for k in range(i + 1, j) if lines[k].strip())
                mapping[key.strip()] = block(i + 1, j, indent(inner))
            else:
                mapping[key.strip()] = None
            i = j
        if seq and mapping:
            raise ValueError(f"{path.name}: a block is both a list and a mapping")
        return seq if seq else mapping

    first = next(i for i, raw in enumerate(lines) if raw.strip())
    out = block(0, len(lines), indent(first))
    if not isinstance(out, dict):
        raise ValueError(f"{path.name}: top level is not a mapping")
    return out


class ThePackageMatchesTheProject(unittest.TestCase):
    def manifest(self) -> dict:
        return load_yaml(PACKAGE / "manifest.yaml")

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
        return load_yaml(PACKAGE / "manifest.yaml")

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



class TheReaderAgreesWithTheRealParser(unittest.TestCase):
    """`load_yaml` exists so the suite needs no third-party parser. It is only
    worth having if it returns what the real one returns, so wherever PyYAML is
    installed - every developer machine, and CI, which installs it for exactly
    this - the two are compared on the files the platform actually reads.
    """

    def test_it_parses_the_manifest_the_way_pyyaml_does(self):
        path = PACKAGE / "manifest.yaml"
        self.assertEqual(load_yaml(path), self._yaml().safe_load(path.read_text()))

    def test_it_refuses_the_backtest_file_rather_than_half_reading_it(self):
        """backtest.yaml nests mappings inside sequences, which this reader
        does not do. Nothing parses it, and the failure must stay loud: a
        reader that quietly dropped every instrument would still return a
        dict."""
        with self.assertRaises(ValueError):
            load_yaml(PACKAGE / "backtest.yaml")

    def test_it_refuses_what_it_cannot_parse_rather_than_guessing(self):
        import tempfile
        for bad in ("a: {b: 1}\n", "a: [1, 2]\n", "a: >\n  folded\n",
                    "a: &x 1\n", "a: *x\n", "---\na: 1\n", "a:\n\tb: 1\n"):
            with self.subTest(bad):
                with tempfile.NamedTemporaryFile(
                        "w", suffix=".yaml", delete=False) as fh:
                    fh.write(bad)
                with self.assertRaises(ValueError):
                    load_yaml(Path(fh.name))

    def _yaml(self):
        try:
            import yaml
        except ImportError:  # pragma: no cover - CI installs it
            self.skipTest("PyYAML absent; the reader stands alone here")
        return yaml


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
        exec(compile(src[start:end], "_repair", "exec"), namespace)
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
