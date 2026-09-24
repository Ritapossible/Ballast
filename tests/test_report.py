"""The public pages must build from any ledger state, including an empty one.

A demo that errors on the day is worth less than no demo, and the handbook makes an
accessible demo a required material.
"""
from __future__ import annotations

import datetime as dt
import os
import re
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from ballast import config, docs_page, report
from ballast.ledger import Ledger


def build_site(entries) -> dict[str, str]:
    """Render every page against a throwaway ledger."""
    with tempfile.TemporaryDirectory() as d:
        ledger_path = Path(d) / "ledger.jsonl"
        lg = Ledger(ledger_path, b"t")
        for kind, body in entries:
            lg.append(kind, body)
        # The comparison index is a separate artifact; a page test must not read
        # whatever the real one happens to contain.
        with mock.patch.object(config, "LEDGER_PATH", ledger_path), \
             mock.patch.object(config, "secret", return_value=b"t"), \
             mock.patch.object(report, "OUT_DIR", Path(d)), \
             mock.patch.object(config, "STATE", Path(d)), \
             mock.patch.object(docs_page, "OUT", Path(d) / "docs.html"):
            pages = {p.name: p.read_text() for p in report.build()}
            pages["docs.html"] = docs_page.build().read_text()
            return pages


POPULATED = [
    ("decision", {"ticker": "ORCL", "session": "2026-09-10", "action": "HEDGE",
                  "sigma_bp": 240.0, "notional_usdt": 1000.0,
                  "rationale": "event reader judged HEDGE",
                  "inputs": {"decided_by": "model"}}),
    ("night_summary", {"session": "2026-09-10", "positions": 1, "hedged": 1,
                       "window_hours": 17.5, "reader": "on"}),
    ("settlement", {"session": "2026-09-10", "rows": [
        {"ticker": "ORCL", "action": "HEDGE", "unhedged_bp": -812.0,
         "realised_bp": -41.0, "counterfactual_bp": -812.0,
         "value_added_bp": 771.0}]}),
]


class TestPages(unittest.TestCase):
    def test_builds_from_an_empty_ledger(self):
        pages = build_site([])
        self.assertEqual(len(pages), len(report.PAGES) + 1)
        for name, html in pages.items():
            self.assertIn("<!doctype html>", html, name)
        self.assertIn("No decisions recorded yet", pages["tonight.html"])
        self.assertIn("Nothing settled yet", pages["settled.html"])

    def test_decisions_render_on_the_tonight_page(self):
        pages = build_site(POPULATED)
        tonight = pages["tonight.html"]
        self.assertIn("ORCL", tonight)
        self.assertIn("event reader judged HEDGE", tonight)
        self.assertIn("model", tonight)

    def test_settlements_render_on_the_settled_page(self):
        settled = build_site(POPULATED)["settled.html"]
        self.assertIn("-41 bp", settled)          # realised
        self.assertIn("-812 bp", settled)         # counterfactual
        self.assertIn("+771 bp", settled)         # the difference

    def test_every_settled_row_can_be_checked_by_subtraction(self):
        """The page tells a reader value added is realised minus "if reversed".
        A row that does not satisfy that is a row nobody can verify - and the
        column was missing entirely until the arithmetic stopped reconciling on
        screen for every refusal."""
        import re
        settled = build_site(POPULATED)["settled.html"]
        row = re.search(r"<tr><td data-label=\"\">.*?</tr>", settled).group(0)
        nums = [int(n.replace(",", "")) for n in
                re.findall(r'data-label="(?:Realised|If reversed|Value added)">'
                           r'([+-][\d,]+) bp', row)]
        self.assertEqual(len(nums), 3, row)
        realised, if_reversed, value_added = nums
        self.assertEqual(realised - if_reversed, value_added)

    def test_states_what_is_not_claimed(self):
        pages = build_site([])
        index = " ".join(pages["index.html"].split())
        evidence = " ".join(pages["evidence.html"].split())
        self.assertIn("priced protection, not alpha", evidence)
        self.assertIn("makes no Sharpe claim", evidence)
        self.assertIn("not claimed", evidence)
        self.assertIn("paper only", evidence)
        self.assertIn("Not the night's risk", index)

    def test_reports_a_broken_chain_rather_than_hiding_it(self):
        with tempfile.TemporaryDirectory() as d:
            ledger_path = Path(d) / "ledger.jsonl"
            Ledger(ledger_path, b"t").append("decision", {"ticker": "X"})
            with mock.patch.object(config, "LEDGER_PATH", ledger_path), \
                 mock.patch.object(config, "secret", return_value=b"wrong"), \
                 mock.patch.object(report, "OUT_DIR", Path(d)):
                pages = {p.name: p.read_text() for p in report.build()}
        self.assertIn("CHAIN BROKEN", pages["tonight.html"])

    def test_no_em_dashes_in_page_templates(self):
        for name, html in build_site([]).items():
            self.assertNotIn("—", html, f"{name} contains an em dash")


class StalenessCase(unittest.TestCase):
    """A stopped scheduler leaves the last good night on the page, which reads as
    a working site. Settlement had been failing on every run and the pages said
    nothing, so the page now states how far behind the ledger is."""

    def _site(self, session: str, now: dt.datetime):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "ledger.jsonl"
            lg = Ledger(path, config.DEV_SECRET)
            lg.append("night_summary", {"session": session, "positions": 1,
                                        "hedged": 0, "window_hours": 17.5})
            with mock.patch.object(config, "LEDGER_PATH", path), \
                 mock.patch.object(config, "secret", return_value=config.DEV_SECRET):
                return report.Site(now=now)

    def test_the_current_session_is_not_flagged(self):
        # 2026-09-10 21:00Z is after that day's 20:00Z close.
        site = self._site("2026-09-10", dt.datetime(2026, 9, 10, 21, tzinfo=dt.timezone.utc))
        self.assertEqual(site.behind, 0)
        self.assertEqual(site.freshness, "")

    def test_the_hour_before_the_run_is_due_is_not_stale(self):
        """The decide cron is an hour after the close. Flagging at the close made
        the page read STALE nightly between 20:00Z and whenever the run landed."""
        site = self._site("2026-09-10", dt.datetime(2026, 9, 11, 20, 58,
                                                    tzinfo=dt.timezone.utc))
        self.assertEqual(site.behind, 0)

    def test_a_run_delayed_three_hours_is_not_stale(self):
        """GitHub delayed one of ours by 3h17m; that must not raise an alarm."""
        site = self._site("2026-09-10", dt.datetime(2026, 9, 11, 23, 30,
                                                    tzinfo=dt.timezone.utc))
        self.assertEqual(site.behind, 0)

    def test_past_the_grace_period_it_is_stale(self):
        site = self._site("2026-09-10", dt.datetime(2026, 9, 12, 0, 30,
                                                    tzinfo=dt.timezone.utc))
        self.assertEqual(site.behind, 1)

    def test_a_missed_run_is_stated_on_the_page(self):
        # Past the grace window on 09-10, so both 09-09 and 09-10 are genuinely due.
        site = self._site("2026-09-08", dt.datetime(2026, 9, 11, 1, tzinfo=dt.timezone.utc))
        self.assertEqual(site.behind, 2)            # 09-09 and 09-10 both missed
        self.assertIn("2 sessions behind", site.freshness)

    def test_holidays_do_not_count_as_missed_sessions(self):
        """Labor Day 2026 is 09-07. Friday 09-04 to Tuesday 09-08 is one session."""
        site = self._site("2026-09-04", dt.datetime(2026, 9, 9, 1, tzinfo=dt.timezone.utc))
        self.assertEqual(site.behind, 1)


class DecisionLagCase(unittest.TestCase):
    """The page must say when the night was decided, derived from the ledger's own
    timestamp for entries written before the field existed."""

    def _site(self, session: str, written: dt.datetime, body_extra=None):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "ledger.jsonl"
            lg = Ledger(path, config.DEV_SECRET)
            body = {"session": session, "positions": 1, "hedged": 0, "window_hours": 17.5}
            body.update(body_extra or {})
            lg.append("night_summary", body, written)
            with mock.patch.object(config, "LEDGER_PATH", path), \
                 mock.patch.object(config, "secret", return_value=config.DEV_SECRET):
                return report.Site(now=written)

    def test_a_prompt_decision_is_reported_plainly(self):
        site = self._site("2026-09-10",
                          dt.datetime(2026, 9, 10, 22, tzinfo=dt.timezone.utc))
        self.assertAlmostEqual(site.decided_after, 2.0, places=1)
        self.assertFalse(site.decided_late)
        self.assertIn("2.0 hours", site.provenance)
        self.assertNotIn("not an ex-ante decision", site.provenance)

    def test_a_window_mostly_gone_is_disclosed_on_the_page(self):
        # 12:45Z the next day is 16.75h after a 20:00Z close - the entry that shipped.
        site = self._site("2026-09-10",
                          dt.datetime(2026, 9, 11, 12, 45, tzinfo=dt.timezone.utc))
        self.assertTrue(site.decided_late)
        self.assertIn("not an ex-ante decision", site.provenance)

    def test_a_recorded_lag_is_preferred_over_the_derived_one(self):
        site = self._site("2026-09-10",
                          dt.datetime(2026, 9, 11, 12, 45, tzinfo=dt.timezone.utc),
                          {"decided_after_close_hours": 1.5})
        self.assertEqual(site.decided_after, 1.5)
        self.assertFalse(site.decided_late)


class LandingWidgetCase(unittest.TestCase):
    """The policy declines about ten nights in twelve, so book order put five
    refusals in the landing page's only live widget and neither hedge - it read
    as a system that does nothing."""

    def _index(self, actions):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "ledger.jsonl"
            lg = Ledger(path, config.DEV_SECRET)
            lg.append("night_summary", {"session": "2026-09-10", "positions": len(actions),
                                        "hedged": sum(a == "HEDGE" for a in actions),
                                        "window_hours": 17.5})
            for ticker, action in actions.items():
                lg.append("decision", {"session": "2026-09-10", "ticker": ticker,
                                       "action": action, "sigma_bp": 100.0,
                                       "notional_usdt": 1000.0, "rationale": "x"})
            with mock.patch.object(config, "LEDGER_PATH", path), \
                 mock.patch.object(config, "secret", return_value=config.DEV_SECRET):
                site = report.Site(now=dt.datetime(2026, 9, 10, 21,
                                                   tzinfo=dt.timezone.utc))
                return site.index()

    def test_hedges_appear_before_refusals(self):
        actions = {t: "NO_HEDGE" for t in
                   ("TSLA", "NVDA", "PLTR", "COIN", "AMD", "MSFT")}
        actions["ORCL"] = "HEDGE"
        rows = re.findall(r'<div class="term-r">.*?</div>', self._index(actions))
        self.assertIn("ORCL", rows[0])

    def test_five_rows_do_not_misrepresent_twelve(self):
        actions = {t: "NO_HEDGE" for t in
                   ("TSLA", "NVDA", "PLTR", "COIN", "AMD", "MSFT")}
        actions["ORCL"] = "HEDGE"
        html = self._index(actions)
        self.assertIn("7 positions \u00b7 1 hedged", html)

    def test_a_short_night_needs_no_count_line(self):
        html = self._index({"ORCL": "HEDGE", "TSLA": "NO_HEDGE"})
        self.assertNotIn("see all", html)


class TileScopeCase(unittest.TestCase):
    """Tiles measure only sessions decided with the corrected calendar - a session
    whose hedges were a night early cannot say how well a hedge works. Excluding it
    raises the mean, so the scope note has to carry the sample size."""

    def _site(self, sessions):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "ledger.jsonl"
            lg = Ledger(path, config.DEV_SECRET)
            for session, va in sessions.items():
                lg.append("night_summary", {"session": session, "positions": 1,
                                            "hedged": 1, "window_hours": 17.5})
                lg.append("settlement", {"session": session, "decisions": 1, "hedged": 1,
                                         "rows": [{"ticker": "ORCL", "action": "HEDGE",
                                                   "unhedged_bp": -400.0, "realised_bp": -10.0,
                                                   "counterfactual_bp": -10.0 - va,
                                                   "value_added_bp": va}]})
            with mock.patch.object(config, "LEDGER_PATH", path), \
                 mock.patch.object(config, "secret", return_value=config.DEV_SECRET):
                return report.Site(now=dt.datetime(2026, 9, 12, 21,
                                                   tzinfo=dt.timezone.utc))

    def test_only_the_affected_hedges_leave_the_tiles(self):
        site = self._site({"2026-09-09": -900.0, "2026-09-10": 300.0})
        self.assertEqual(len(site.clean), 1)
        self.assertEqual(site.mean_va, 300.0)          # not the -300 average of both
        self.assertEqual(len(site.hedges), 1)

    def test_a_refusal_on_an_affected_night_still_counts(self):
        """The fault could add a hedge, never remove one, so a refusal that night
        would have been a refusal under the corrected rule too. Excluding it would
        drop a sound decision and overstate the result."""
        row = {"ticker": "MU", "action": "NO_HEDGE", "unhedged_bp": -413.0,
               "realised_bp": -413.0, "counterfactual_bp": -18.0,
               "value_added_bp": -395.0, "session": "2026-09-09"}
        self.assertFalse(report._selector_affected(row))
        row["action"] = "HEDGE"
        self.assertTrue(report._selector_affected(row))
        row["session"] = "2026-09-10"
        self.assertFalse(report._selector_affected(row))

    def test_it_stays_in_the_table(self):
        site = self._site({"2026-09-09": -900.0, "2026-09-10": 300.0})
        self.assertEqual(len(site.rows), 2, "an excluded row was dropped from the record")
        self.assertIn("2026-09-09", report._settled(site.rows))

    def test_the_scope_note_names_the_excluded_rows(self):
        flat = " ".join(self._site({"2026-09-09": -900.0,
                                    "2026-09-10": 300.0}).tile_scope.split())
        self.assertIn("1 hedges are excluded", flat.replace("1 hedges", "1 hedges"))
        self.assertIn("2026-09-09", flat)
        self.assertIn("refusals that night stand", flat)

    def test_no_scope_note_without_an_exclusion(self):
        flat = " ".join(self._site({"2026-09-10": 300.0}).tile_scope.split())
        self.assertNotIn("excluded", flat)
        self.assertIn("1 night", flat)

    def test_the_marker_reads_as_what_happened(self):
        html = report._settled([{"ticker": "ORCL", "action": "HEDGE",
                                 "unhedged_bp": -390.0, "realised_bp": -14.0,
                                 "value_added_bp": 376.0, "session": "2026-09-09"}])
        self.assertIn("hedged a night early", html)


class ProvenanceCase(unittest.TestCase):
    """The instrument claim is only true while every price really does come from
    the traded books. A test, not a sentence, because the sentence is the risk."""

    def _site(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "ledger.jsonl"
            Ledger(path, config.DEV_SECRET).append("night_summary", {"session": "2026-09-10"})
            with mock.patch.object(config, "LEDGER_PATH", path), \
                 mock.patch.object(config, "secret", return_value=config.DEV_SECRET):
                return report.Site(now=dt.datetime(2026, 9, 10, 21,
                                                   tzinfo=dt.timezone.utc))

    def test_no_price_source_outside_bitget(self):
        """The page states there is no equity feed. Verify it against the code."""
        market = (Path(__file__).resolve().parent.parent / "ballast" / "market.py").read_text()
        hosts = set(re.findall(r"https://([a-z0-9.]+)", market))
        self.assertEqual(hosts, {"api.bitget.com"}, f"market.py reaches {hosts}")

    def test_the_block_names_every_source_and_its_job(self):
        block = self._site().provenance_block
        for source in ("Bitget spot", "Bitget USDT-futures", "Nasdaq",
                       "Google News", "Qwen"):
            self.assertIn(source, block)
        self.assertIn("dates only, never a price", block)

    def test_it_states_the_instrument_distinction(self):
        # Normalised: the source wraps, so a line break can fall mid-phrase.
        flat = " ".join(self._site().provenance_block.split())
        self.assertIn("trades continuously", flat)
        self.assertIn("no equity feed anywhere in the codebase", flat)

    def test_it_is_on_the_evidence_page(self):
        site = self._site()
        self.assertIn(site.provenance_block, site.evidence_page())


class SettledTableCase(unittest.TestCase):
    """Two nights in, the table showed ORCL twice with near-identical numbers and
    nothing to tell them apart - which reads as a duplicate-row bug."""

    def test_every_row_names_its_session(self):
        rows = [{"ticker": "ORCL", "action": "HEDGE", "unhedged_bp": -390.0,
                 "realised_bp": -14.0, "value_added_bp": 376.0, "session": "2026-09-09"},
                {"ticker": "ORCL", "action": "HEDGE", "unhedged_bp": -384.0,
                 "realised_bp": -11.0, "value_added_bp": 373.0, "session": "2026-09-10"}]
        html = report._settled(rows)
        self.assertIn("2026-09-09", html)
        self.assertIn("2026-09-10", html)
        self.assertIn('data-label="Session"', html)

    def test_rows_group_by_night_newest_first(self):
        rows = [{"ticker": "SMALL", "action": "NO_HEDGE", "unhedged_bp": -10.0,
                 "realised_bp": -10.0, "value_added_bp": -5.0, "session": "2026-09-10"},
                {"ticker": "BIG", "action": "NO_HEDGE", "unhedged_bp": -900.0,
                 "realised_bp": -900.0, "value_added_bp": -880.0, "session": "2026-09-09"}]
        order = re.findall(r"<strong>([A-Z]+)</strong>", report._settled(rows))
        self.assertEqual(order, ["SMALL", "BIG"], "a bigger move from an older night led")


class SelectorMarkCase(unittest.TestCase):
    """A results page needs to say which rows are unsound, not why the bug happened.

    The mechanism is written up once, under defects. A hundred-word post-mortem in a
    callout here repeated what the tile scope note already said - the same
    duplication the roadmap callout was removed for.
    """

    def _rows(self, session):
        return [{"ticker": "ORCL", "action": "HEDGE", "unhedged_bp": -390.0,
                 "realised_bp": -14.0, "value_added_bp": 376.0, "session": session}]

    def test_an_affected_row_is_marked(self):
        html = report._settled(self._rows("2026-09-09"))
        self.assertIn("hedged a night early", html)

    def test_a_refusal_on_the_same_night_is_not_marked(self):
        rows = self._rows("2026-09-09")
        rows[0]["action"] = "NO_HEDGE"
        self.assertNotIn("hedged a night early", report._settled(rows))

    def test_a_clean_row_is_not(self):
        html = report._settled(self._rows("2026-09-10"))
        self.assertNotIn("hedged a night early", html)

    def test_the_page_points_at_the_full_write_up_rather_than_repeating_it(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "ledger.jsonl"
            lg = Ledger(path, config.DEV_SECRET)
            lg.append("night_summary", {"session": "2026-09-09", "positions": 1,
                                        "hedged": 1, "window_hours": 17.5})
            lg.append("settlement", {"session": "2026-09-09", "decisions": 1,
                                     "hedged": 1, "rows": self._rows("2026-09-09")})
            with mock.patch.object(config, "LEDGER_PATH", path), \
                 mock.patch.object(config, "secret", return_value=config.DEV_SECRET):
                page = report.Site(now=dt.datetime(2026, 9, 10, 21,
                                                   tzinfo=dt.timezone.utc)).settled_page()
        self.assertIn("docs.html#defects", page)
        self.assertNotIn("The calendar rule matched", page)


class DevKeyBuildGuard(unittest.TestCase):
    """The command line must not publish pages without the real signing key.

    Verification runs at build time and its verdict is a fixed string in the
    HTML, so a development-key rebuild over a real-key ledger publishes
    "CHAIN BROKEN" about a ledger that is intact.
    """

    def test_refuses_without_a_signing_key(self):
        with mock.patch.dict(os.environ, {}, clear=True), \
             self.assertRaises(config.UnsignedError):
            config.refuse_dev_build()

    def test_refuses_with_only_the_development_key(self):
        with mock.patch.dict(os.environ, {"BALLAST_DEV_SECRET": "1"}, clear=True), \
             self.assertRaises(config.UnsignedError):
            config.refuse_dev_build()

    def test_allows_a_deliberate_local_preview(self):
        env = {"BALLAST_DEV_SECRET": "1", config.DEV_BUILD_OVERRIDE: "1"}
        with mock.patch.dict(os.environ, env, clear=True):
            config.refuse_dev_build()

    def test_allows_a_real_key(self):
        with mock.patch.dict(os.environ, {"BALLAST_SECRET": "x"}, clear=True):
            config.refuse_dev_build()


class NoLiteralMeasurementsCase(unittest.TestCase):
    """Measured figures must be rendered from facts.json, never typed.

    The universe counts drifted 224/704 -> 241/1,173 while the README said the old
    ones, which is why facts.json exists. Four more measurements were still typed
    into the page builders after that: MSFT's and AMD's worst nights in three
    places, and the whole out-of-sample paragraph - written the same day the rule
    was restated.
    """

    def test_the_worst_night_pairs_come_from_the_measurement(self):
        from ballast import facts
        values = dict(facts.load())
        values["tail"] = [{"name": "MSFT", "worst_unhedged": 4321, "worst_hedged": 21,
                           "p95_unhedged": 100, "p95_hedged": 10, "nights": 200}]
        self.assertEqual(facts.worst_night(values, "MSFT"), "4,321 bp to 21 bp")
        self.assertEqual(facts.worst_night(values, "NOPE"), "-")

    def test_no_builder_types_a_measured_pair(self):
        import re
        for module in ("ballast/report.py", "ballast/docs_page.py"):
            src = Path(__file__).resolve().parent.parent.joinpath(module).read_text()
            typed = re.findall(r"\d,\d{3} bp to \d+ bp", src)
            self.assertEqual(typed, [], f"{module} types a measured pair: {typed}")

    def test_the_docs_out_of_sample_figures_are_not_typed(self):
        src = (Path(__file__).resolve().parent.parent
               / "ballast" / "docs_page.py").read_text()
        oos = src[src.index('id="oos"'):src.index('id="roadmap"')]
        self.assertNotIn("0.996", oos)
        self.assertNotIn("0.009", oos)
        self.assertIn("F['oos']", oos)


class ClaimTableCase(unittest.TestCase):
    """The claim table is the complete statement of what the project asserts, so
    a count in it going stale is the table asserting something untrue. It said
    "18 red-team tests" while the file held 25, and "100-260 nights" against a
    sample running to 264."""

    def test_the_red_team_count_is_counted(self):
        from ballast import suite
        path = Path(__file__).resolve().parent / "test_enforcer.py"
        self.assertEqual(suite.red_team(), path.read_text().count("def test_"))

    def test_the_night_range_comes_from_the_sample(self):
        from ballast import report
        f = {"tail": [{"name": "A", "nights": 100}, {"name": "B", "nights": 264}]}
        self.assertEqual(report._nights_range(f), "100-264")

    def test_no_count_in_the_table_is_a_literal(self):
        import re
        src = (Path(__file__).resolve().parent.parent / "ballast" / "report.py").read_text()
        table = src[src.index("def claims("):src.index("class Site")]
        for typed in re.findall(r'"\s*(\d+) red-team|(\d+)-(\d+) nights', table):
            self.fail(f"claim table types a count: {typed}")

    def test_the_out_of_sample_result_is_claimed(self):
        from ballast import facts, report
        claims = [c for c, _, _ in report.claims(facts.load())]
        self.assertTrue(any("out of sample" in c for c in claims),
                        "the strongest evidence on the site is not in the claim table")


class SettledTape(unittest.TestCase):
    """History beside the live state, never instead of it.

    Most nights are refusals - Gate 1a is why - so a reader landing on twelve
    NO_HEDGE cannot tell a selective agent from a broken one. The fix was NOT
    to pin a flattering past night as the hero: it is to show the last settled
    night whatever it was, and only name an earlier hedge when that night had
    none.
    """

    @staticmethod
    def tape(settlements):
        return report.Site._settled_tape(SimpleNamespace(settlements=settlements))

    def test_no_settlements_means_no_tape(self):
        self.assertEqual(self.tape([]), "")

    def test_it_reports_the_most_recent_settled_night(self):
        out = self.tape([
            {"session": "2026-09-01", "hedged": 3, "hedges_that_cut": 3},
            {"session": "2026-09-02", "hedged": 1, "hedges_that_cut": 0},
        ])
        self.assertIn("settled 2026-09-02", out)
        self.assertNotIn("2026-09-01", out)

    def test_it_does_not_pick_the_flattering_night(self):
        """The whole point. A later dull night wins over an earlier good one."""
        out = self.tape([
            {"session": "2026-09-01", "hedged": 5, "hedges_that_cut": 5},
            {"session": "2026-09-02", "hedged": 2, "hedges_that_cut": 0},
        ])
        self.assertIn("2 hedged, 0 cut the move", out)
        self.assertNotIn("5 cut the move", out)

    def test_ledger_order_does_not_decide_which_night_is_last(self):
        """Entries are appended, but the session date is what makes one latest."""
        out = self.tape([
            {"session": "2026-09-09", "hedged": 1, "hedges_that_cut": 1},
            {"session": "2026-09-02", "hedged": 4, "hedges_that_cut": 4},
        ])
        self.assertIn("settled 2026-09-09", out)

    def test_a_quiet_last_night_still_says_when_it_last_acted(self):
        out = self.tape([
            {"session": "2026-09-01", "hedged": 2, "hedges_that_cut": 1},
            {"session": "2026-09-02", "hedged": 0, "hedges_that_cut": 0},
        ])
        self.assertIn("settled 2026-09-02", out)
        self.assertIn("no hedge was called for", out)
        self.assertIn("last settled hedge 2026-09-01", out)
        self.assertIn("1 of 2 cut the move", out)

    def test_the_older_hedge_is_labelled_settled_not_last(self):
        """This walk is over settled sessions, and it sits under a tile showing
        tonight's decisions - which can carry a HEDGE on a later date.

        Read as a bare "last hedge", the two rows contradict each other on the
        same screen. The figure beside it is a graded outcome, so the label has
        to say settled; changing the date to tonight's would claim a grade for
        a night nothing has settled.
        """
        out = self.tape([
            {"session": "2026-09-16", "hedged": 1, "hedges_that_cut": 1},
            {"session": "2026-09-17", "hedged": 0, "hedges_that_cut": 0},
        ])
        self.assertIn("last settled hedge", out)
        self.assertNotRegex(out, r"(?<!settled )last hedge")

    def test_a_night_that_hedged_does_not_also_quote_an_older_one(self):
        out = self.tape([
            {"session": "2026-09-01", "hedged": 9, "hedges_that_cut": 9},
            {"session": "2026-09-02", "hedged": 1, "hedges_that_cut": 1},
        ])
        self.assertNotIn("last hedge", out)

    def test_never_having_hedged_is_not_papered_over(self):
        out = self.tape([{"session": "2026-09-02", "hedged": 0,
                          "hedges_that_cut": 0}])
        self.assertIn("no hedge was called for", out)
        self.assertNotIn("last hedge", out)

    def test_it_links_to_the_settled_page_not_an_assertion(self):
        out = self.tape([{"session": "2026-09-02", "hedged": 1,
                          "hedges_that_cut": 1}])
        self.assertIn('href="settled.html"', out)


class TheTonightCardShowsTheModelsWork(unittest.TestCase):
    """The page used to print a template string on every card.

    `rationale` comes from `policy.decide`, so twelve names the model had read
    twelve different ways all rendered as the same sentence - and a reader whose
    answer a gate had thrown out still rendered as MODEL. Both made the reader look
    like a rubber stamp on a page whose whole argument is that it is not one.
    """

    def card(self, **over) -> str:
        body = {"ticker": "NVDA", "session": "2026-09-10", "action": "NO_HEDGE",
                "sigma_bp": 218.0, "notional_usdt": 965.0,
                "rationale": "event reader judged NO_HEDGE - nothing tonight can move this name",
                "inputs": {"decided_by": "model"},
                "reader": {"accepted": True, "judgment": "NO_HEDGE",
                           "reasoning": "Routine insider selling, no overnight catalyst.",
                           "verbatim_quote": "NVIDIA CFO sells 34,918 shares"},
                "news": {"headlines_fetched": 12, "in_window": 8, "shown": 8,
                         "source": "window"}}
        body.update(over)
        return build_site([
            ("decision", body),
            ("night_summary", {"session": "2026-09-10", "positions": 1, "hedged": 0,
                               "window_hours": 17.5, "reader": "on"}),
        ])["tonight.html"]

    def test_the_models_own_reasoning_is_shown_not_the_template(self):
        out = self.card()
        self.assertIn("Routine insider selling", out)
        self.assertNotIn("nothing tonight can move this name", out)

    def test_the_quote_it_was_grounded_on_is_shown(self):
        self.assertIn("NVIDIA CFO sells 34,918 shares", self.card())

    def test_a_judgment_with_no_quote_says_so_rather_than_showing_nothing(self):
        out = self.card(reader={"accepted": True, "judgment": "NO_HEDGE",
                                "reasoning": "Nothing specific tonight.",
                                "verbatim_quote": ""})
        self.assertIn("no quote - judged on the absence of an event", out)

    def test_what_the_model_was_shown_is_on_the_card(self):
        self.assertIn("12 headlines", self.card())
        self.assertIn("8 in tonight&#x27;s window", self.card())

    def test_a_fallback_brief_is_not_passed_off_as_tonights_news(self):
        out = self.card(news={"headlines_fetched": 12, "in_window": 0, "shown": 8,
                              "source": "recent_fallback"})
        self.assertIn("none in tonight&#x27;s window, showed 8 recent", out)

    def test_an_unreachable_feed_is_stated(self):
        out = self.card(news={"source": "unavailable", "error": "timeout",
                              "headlines_fetched": 0, "in_window": 0, "shown": 0})
        self.assertIn("news feed unavailable", out)

    def test_a_gated_reader_is_never_labelled_model(self):
        """A refused answer handed the night back to the rule; the card must say so."""
        out = self.card(
            inputs={"decided_by": "rule"},
            reader={"accepted": False, "rejected_because": "quote_not_in_sources",
                    "judgment": "ABSTAIN"})
        self.assertIn("ABSTAIN", out)
        self.assertIn("its quote was not in the supplied headlines", out)
        self.assertNotIn('class="tag on">model', out)

    def test_every_gate_has_an_english_sentence(self):
        from ballast.reader import RejectReason
        for reason in RejectReason:
            self.assertIn(reason.value, report.GATE_ENGLISH, reason.value)

    def test_hedges_are_listed_before_refusals(self):
        pages = build_site([
            ("decision", {"ticker": "AAA", "session": "2026-09-10", "action": "NO_HEDGE",
                          "sigma_bp": 1.0, "notional_usdt": 1.0, "rationale": "r",
                          "inputs": {"decided_by": "rule"}}),
            ("decision", {"ticker": "ZZZ", "session": "2026-09-10", "action": "HEDGE",
                          "sigma_bp": 1.0, "notional_usdt": 1.0, "rationale": "r",
                          "inputs": {"decided_by": "rule"}}),
            ("night_summary", {"session": "2026-09-10", "positions": 2, "hedged": 1,
                               "window_hours": 17.5, "reader": "on"}),
        ])["tonight.html"]
        body = pages.split("<tbody>")[1]
        self.assertLess(body.index("ZZZ"), body.index("AAA"))

    def test_a_ticker_carries_the_company_it_names(self):
        self.assertIn("NVIDIA", self.card())
        self.assertIn("Costco", self.card(ticker="COST"))

    def test_the_strip_says_why_a_night_of_refusals_is_expected(self):
        out = self.card()
        self.assertIn("left exposed, deliberately", out)
        # One line and a link. The full argument lives at docs.html#selector and
        # used to be repeated here in full, above the decisions.
        self.assertIn("not volatility", out)
        self.assertIn('href="docs.html#selector"', out)


class ARefusalIsNotColouredLikeAVerdict(unittest.TestCase):
    """Colour is a verdict, and the same page spends a paragraph refusing to give
    a refusal one. Green on a refused rally says "we were right to stand down" when
    all it means is that the position rose."""

    def settled(self, rows) -> str:
        return build_site([
            ("night_summary", {"session": "2026-09-16", "positions": len(rows),
                               "hedged": 0, "window_hours": 17.5, "reader": "on"}),
            ("settlement", {"session": "2026-09-16", "rows": rows}),
        ])["settled.html"]

    def row(self, **over) -> dict:
        r = {"ticker": "MU", "action": "NO_HEDGE", "unhedged_bp": 567.0,
             "realised_bp": 567.0, "counterfactual_bp": -8.0, "value_added_bp": 575.0}
        r.update(over)
        return r

    def cell(self, html_text: str, value: str) -> str:
        import re as _re
        m = _re.search(r'<td class="num ([a-z]+)"[^>]*>' + _re.escape(value), html_text)
        self.assertIsNotNone(m, f"no value-added cell for {value}")
        return m.group(1)

    def test_a_refused_rally_is_not_green(self):
        out = self.settled([self.row()])
        self.assertEqual(self.cell(out, "+575 bp"), "mid")

    def test_a_refused_fall_is_not_red(self):
        out = self.settled([self.row(unhedged_bp=-500.0, realised_bp=-500.0,
                                     value_added_bp=-490.0)])
        self.assertEqual(self.cell(out, "-490 bp"), "mid")

    def test_a_hedge_that_paid_is_still_green(self):
        out = self.settled([self.row(ticker="COST", action="HEDGE", unhedged_bp=-40.0,
                                     realised_bp=-11.0, counterfactual_bp=-40.0,
                                     value_added_bp=28.0)])
        self.assertEqual(self.cell(out, "+28 bp"), "pos")

    def test_a_hedge_that_cost_is_still_red(self):
        out = self.settled([self.row(ticker="MU", action="HEDGE", unhedged_bp=10.0,
                                     realised_bp=-107.0, counterfactual_bp=10.0,
                                     value_added_bp=-117.0)])
        self.assertEqual(self.cell(out, "-117 bp"), "neg")

    def test_the_page_says_why_only_hedges_are_coloured(self):
        self.assertIn("Only hedges are coloured", self.settled([self.row()]))

    def test_the_counterfactual_column_names_the_choice_not_taken(self):
        out = self.settled([self.row()])
        self.assertIn("If reversed", out)


class TheVenueIsOnThePage(unittest.TestCase):
    """The site said nothing about execution, which hid the strongest piece of
    infrastructure evidence in the project: the Agent Hub route runs on every
    scheduled night, and when the exchange refuses the order Ballast records the
    refusal verbatim and simulates instead. A page showing only a simulated fill
    looks like a project that never attempted the integration."""

    REFUSAL = "exit 1: HTTP 400 from Bitget: exchange environment is incorrect"

    def page(self, summary_extra: dict, fill: dict | None) -> str:
        decision = {"ticker": "COIN", "session": "2026-09-18", "action": "HEDGE",
                    "sigma_bp": 388.0, "notional_usdt": 1074.0, "rationale": "r",
                    "inputs": {"decided_by": "model"}}
        if fill is not None:
            decision["fill"] = fill
        return build_site([
            ("decision", decision),
            ("night_summary", dict({"session": "2026-09-18", "positions": 1,
                                    "hedged": 1, "window_hours": 17.5,
                                    "reader": "on"}, **summary_extra)),
        ])["tonight.html"]

    def test_a_refusal_is_quoted_in_the_exchanges_own_words(self):
        out = self.page({"venue": "bgc-paper",
                         "venue_detail": "Bitget Agent Hub, paper-trading"},
                        {"venue": "simulated", "venue_fallback": self.REFUSAL})
        self.assertIn("Bitget Agent Hub, paper-trading", out)
        # The page prints "1,074 hedged". Someone reading that number has to be
        # able to see, without leaving the page, that no exchange filled it. The
        # exchange's verbatim words live in the docs section; the fact stays here.
        self.assertIn("fills are simulated", out)
        self.assertIn("no fill here claims an exchange order id", out)
        self.assertIn('href="docs.html#execution"', out)

    def test_a_real_order_id_is_reported_as_one(self):
        out = self.page({"venue": "bgc-paper",
                         "venue_detail": "Bitget Agent Hub, paper-trading"},
                        {"venue": "bgc-paper", "orderId": "1234567890"})
        self.assertIn("fills returned an exchange order id", out)
        self.assertNotIn("fills are simulated", out)

    def test_simulation_says_no_order_was_sent(self):
        out = self.page({"venue": "simulated", "venue_detail": "BITGET_API_KEY unset"},
                        {"venue": "simulated"})
        self.assertIn("No order was sent to an exchange", out)
        self.assertNotIn("bgc --paper-trading", out)

    def test_a_night_with_no_venue_recorded_claims_nothing(self):
        self.assertNotIn("Execution", self.page({}, None))

    def test_the_refusal_links_to_the_explanation_rather_than_repeating_it(self):
        """The reason belongs in the docs; the page needs only the fact and a link.

        Roughly 230 words of prose sat between the tiles and the decisions, which
        buried what the page exists to show. The measurement itself - nine demo
        contracts, none of this book's twelve - is not dropped, only moved.
        """
        out = self.page({"venue": "bgc-paper",
                         "venue_detail": "Bitget Agent Hub, paper-trading"},
                        {"venue": "simulated", "venue_fallback": self.REFUSAL})
        self.assertIn('href="docs.html#execution"', out)
        self.assertNotIn("productType=SUSDT-FUTURES", out)

    def test_the_docs_carry_the_measurement_the_page_no_longer_repeats(self):
        """Moved, not dropped - with the command that checks it."""
        import tempfile
        from unittest import mock

        from ballast import config, docs_page
        from ballast.ledger import Ledger
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "ledger.jsonl"
            Ledger(path, b"t").append("night_summary", {"session": "2026-09-18"})
            with mock.patch.object(config, "LEDGER_PATH", path), \
                 mock.patch.object(config, "secret", return_value=b"t"), \
                 mock.patch.object(config, "STATE", Path(d)), \
                 mock.patch.object(docs_page, "OUT", Path(d) / "docs.html"):
                out = docs_page.build().read_text()
        self.assertIn('id="execution"', out)
        self.assertIn("exchange environment is incorrect", out)
        self.assertIn("None of the twelve stocks in this book trades there", out)
        self.assertIn("productType=SUSDT-FUTURES", out)
        self.assertIn("no fill on this ledger carries", out.lower())

    def test_the_explanation_is_not_offered_when_nothing_failed(self):
        out = self.page({"venue": "bgc-paper",
                         "venue_detail": "Bitget Agent Hub, paper-trading"},
                        {"venue": "bgc-paper", "orderId": "1234567890"})
        self.assertNotIn("Why it refuses", out)


class TheCostSentenceAddsUp(unittest.TestCase):
    """The landing page said the hedge cost 12 bp "less the funding a short
    collects, which averages 11 bp a night".

    11.3 is the cost NET of funding, not the funding. The real credit is the
    difference, 0.7 bp - so the sentence overstated what funding gives back by
    about sixteen times, in the flattering direction, on the first screen a
    judge sees. Three figures that each came from facts.json, arranged into a
    claim none of them supported.
    """

    def facts(self) -> dict:
        from ballast import facts
        return facts.load()

    def docs_page(self) -> str:
        """The documentation page, where the cost breakdown lives."""
        import tempfile
        from pathlib import Path as P
        from unittest import mock

        from ballast import config, docs_page
        from ballast.ledger import Ledger
        with tempfile.TemporaryDirectory() as d:
            path = P(d) / "ledger.jsonl"
            Ledger(path, b"t").append("night_summary", {"session": "2026-09-18"})
            with mock.patch.object(config, "LEDGER_PATH", path), \
                 mock.patch.object(config, "secret", return_value=b"t"), \
                 mock.patch.object(config, "STATE", P(d)), \
                 mock.patch.object(docs_page, "OUT", P(d) / "docs.html"):
                return docs_page.build().read_text()

    def test_the_credit_quoted_is_gross_minus_net(self):
        import re
        f = self.facts()
        page = build_site([])["index.html"]
        quoted = re.search(r"net of the ([\d.]+) bp", " ".join(page.split()))
        self.assertIsNotNone(quoted, "the cost sentence lost its funding figure")
        self.assertAlmostEqual(
            float(quoted.group(1)),
            f["hedge_cost_gross_bp"] - f["hedge_cost_bp"], places=1,
            msg="the funding credit on the page is not gross minus net")

    def test_the_frozen_credit_and_the_measured_one_are_both_shown(self):
        """These two are allowed to differ, and must both be visible.

        The net cost is frozen on purpose: the settled table charges it on every
        night, and re-pricing a hedge part-way through a competition record
        would make that table incomparable with itself. Funding is re-measured
        nightly, so it drifts away from the frozen credit.

        This test used to assert they were equal, which was true on the day the
        record opened and quietly false afterwards - it went red because the
        market moved, not because the page was wrong. What matters is that the
        page does not present the frozen credit as today's measurement.
        """
        f = self.facts()
        measured = (f.get("funding") or {}).get("mean_bp")
        if measured is None:
            self.skipTest("no funding measurement in facts.json")
        page = " ".join(self.docs_page().split())
        self.assertIn("frozen when the record", page,
                      "the page does not say the credit is frozen")
        self.assertIn(f"averaging {measured:.2f} bp", page,
                      "the page does not show the re-measured funding average")


class TheToolchainIsStatedOnThePage(unittest.TestCase):
    """The submission claims five Bitget components. Two of them are reachable
    but returning nothing, and for a while the site mentioned none of the five.

    A form that lists an integration the demo never shows is overclaiming, and
    the two that carry no data are exactly the ones a judge would assume work.
    """

    def docs(self) -> str:
        import tempfile
        from unittest import mock

        from ballast import config, docs_page
        from ballast.ledger import Ledger
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "ledger.jsonl"
            Ledger(path, b"t").append("night_summary", {"session": "2026-09-18"})
            with mock.patch.object(config, "LEDGER_PATH", path), \
                 mock.patch.object(config, "secret", return_value=b"t"), \
                 mock.patch.object(config, "STATE", Path(d)), \
                 mock.patch.object(docs_page, "OUT", Path(d) / "docs.html"):
                return docs_page.build().read_text()

    def test_every_claimed_component_appears(self):
        page = self.docs()
        for component in ("bgc", "Qwen", "bitget-mcp-server", "bitget-signal",
                          "Playbook"):
            self.assertIn(component, page, f"{component} is claimed but not shown")

    def test_the_component_that_returns_nothing_says_so(self):
        """bitget-mcp-server spent days at 503 and now answers, so the page may
        only cite that 503 in the past tense."""
        page = " ".join(self.docs().split())
        self.assertIn("0 articles across those 44 feeds", page)
        self.assertNotIn("answers <strong>503</strong>", self.docs(),
                         "the page still reports the MCP upstream as down")

    def test_the_signal_figures_come_from_the_probe_file(self):
        """The bitget-signal row said all 19 tools returned an empty envelope,
        and that this was "confirmed to be the service and not this client".
        Both halves were false: every tool requires an `action`, a call without
        one is answered rather than rejected, and the one tool that does carry
        data - `technical_analysis` - replies to a bare call with
        `{"error": "Unknown action: "}`, which reads as empty.

        Every figure the row now quotes has to match state/signal_probe.json.
        Bare numbers would be useless here - "5", "9" and "44" all appear
        elsewhere on this page - so each one is asserted inside the sentence
        that makes the claim.
        """
        import json
        from pathlib import Path as P

        probe = json.loads(
            (P(__file__).resolve().parent.parent / "state" / "signal_probe.json")
            .read_text())
        counts, cov = probe["counts"], probe["coverage"]
        page = " ".join(self.docs().split())

        self.assertIn(
            f"<strong>{counts['catalog_with_data']} of {counts['catalog_probed']} "
            "catalogue actions</strong>", page,
            "the page does not say how many catalogue actions answered")
        self.assertIn(
            f"<strong>{counts['live_with_data']} of {counts['live_probed']} "
            "fetch-backed actions</strong>", page,
            "the page does not say how many live actions carried data")

        feeds = next(r["count"] for r in probe["rows"]
                     if (r["tool"], r["action"]) == ("news_feed", "sources"))
        articles = next(r["count"] for r in probe["rows"]
                        if (r["tool"], r["action"]) == ("news_feed", "latest"))
        self.assertIn(f"lists <strong>{feeds} feeds</strong>", page,
                      f"the page does not say the aggregator lists {feeds} feeds")
        self.assertIn(
            f"<strong>{articles} articles across those {feeds} feeds</strong>", page,
            f"the page does not say {articles} articles across {feeds} feeds")

        self.assertIn(
            f"<strong>{len(cov['answered'])} of the {cov['asked']} names in this book</strong>",
            page, "the page does not state the measured book coverage")
        self.assertIn(
            "<strong>" + ", ".join(cov["missing"][:-1]) + f" and {cov['missing'][-1]}</strong>",
            page, f"the page does not name the uncovered tickers {cov['missing']}")

        # The control ticker is what makes the indicators evidence rather than
        # decoration. If the service ever starts answering for it, the numbers
        # stop meaning anything and this sentence has to come off the page.
        self.assertTrue(cov["control_refused"],
                        f"{cov['control_ticker']} was answered, so the RSIs prove nothing")
        self.assertIn(f"<code>{cov['control_ticker']}</code> is refused", page,
                      "the page does not name the control ticker it relies on")

    def test_the_page_retracts_the_claim_it_got_wrong(self):
        """A correction that quietly deletes the wrong sentence teaches nobody.

        The old claim was specific - "confirmed to be the service and not this
        client" - so the page has to carry the retraction, not just the fix.
        """
        page = " ".join(self.docs().split())
        self.assertNotIn("Confirmed to be the service and not this client", page,
                         "the page still asserts the claim that was disproved")
        self.assertIn("This row used to", page,
                      "the page corrects the figure without admitting the claim")
        self.assertIn("Unknown action: ", page,
                      "the page does not show the reply that caused the error")

    def test_the_crosscheck_numbers_come_from_the_crosscheck_file(self):
        """The page claimed the upstream answered 503 and that every row was
        recorded `unknown`, while state/calendar_crosscheck.json sitting beside
        it said 96 checked, 0 unknown, 92 agreed, 4 disagreed. Prose and
        measurement disagreed for days and nothing failed.

        Every figure the page quotes about the second opinion now has to match
        that file.
        """
        import json
        from pathlib import Path as P

        path = P(__file__).resolve().parent.parent / "state" / "calendar_crosscheck.json"
        counts = json.loads(path.read_text())["counts"]
        page = " ".join(self.docs().split())
        # Bare numbers are useless here: "96" also appears in the Qwen row and
        # "4" appears all over the page, so the first version of this test
        # passed with every count wrong. The figures have to be asserted inside
        # the sentence that makes the claim.
        # Case-insensitive: the sentence is rendered from the file now and
        # starts with "All". Pinning the lowercase spelling made this test a
        # check on capitalisation rather than on the figure it guards.
        self.assertIn(f"all <strong>{counts['checked']}</strong> decisions are checked",
                      page.lower(),
                      f"the page does not say {counts['checked']} decisions were checked")
        self.assertIn(f"<strong>{counts['agreed']} agree, {counts['disagreed']} do not</strong>",
                      page,
                      f"the page does not say {counts['agreed']} agree and "
                      f"{counts['disagreed']} do not")
        if counts["unknown"] == 0:
            self.assertIn("nothing recorded unknown", page,
                          "0 unknown rows, but the page does not say so")
        self.assertEqual(counts["agreed"] + counts["disagreed"], counts["checked"],
                         "the crosscheck file does not add up")

    def test_the_playbook_number_is_not_passed_off_as_the_product_metric(self):
        """It prices one leg. Ballast's claim is two-legged drawdown."""
        page = " ".join(self.docs().split())
        self.assertIn("pbrun-60a1da0970b5", page)
        self.assertIn("protection leg alone", page)
        self.assertIn("not this product", page)

    def test_the_negative_sharpe_is_not_hidden(self):
        self.assertIn("0.76 Sharpe", " ".join(self.docs().split()))

    def test_the_return_percentage_carries_the_denominator_it_is_on(self):
        """The run record calls it `metrics_basis: strategy` - the platform
        divides net_pnl by margin_budget, not by the account.

        So -1.48% is -29.62 USDT against 2,000, while the account the backtest
        ran in moved -0.03%. A reader who assumes account basis reads a loss
        fifty times the size of the one that happened. The page states which
        denominator it is quoting, and the two figures must agree with each
        other: -29.62 / 2000 is -1.481%.
        """
        page = " ".join(self.docs().split())
        self.assertIn("strategy basis", page)
        self.assertIn("2,000 USDT margin budget", page)
        self.assertIn("29.62 USDT", page)

    def test_both_denominators_are_the_same_loss(self):
        """The page quotes one run on two bases, so the two must reconcile.

        -29.619686 USDT is -1.481% of a 2,000 margin budget and -0.0296% of the
        100,000 the sandbox opened with. Both figures are on the page; if either
        is edited alone, the run has silently become two different runs. The
        account-basis pair was checked against `official_metrics` on the
        published listing, which carries net_pnl and starting_balance directly.
        """
        page = " ".join(self.docs().split())
        self.assertAlmostEqual(-29.619686 / 100_000 * 100, -0.0296, places=4)
        self.assertIn("&minus;1.48% return", page,
                      "the strategy-basis return is not on the page")
        self.assertIn("&minus;0.03% return and 0.08% drawdown", page,
                      "the account-basis pair is not on the page")
        self.assertIn("<code>net_pnl</code> and <code>starting_balance</code> directly", page,
                      "the page does not say where the account-basis pair comes from")

    def test_the_studio_state_is_not_stated_two_ways_at_once(self):
        """Paper Degraded cleared to Paper Running. A page that reports the
        cleared state as current is the 503 mistake again - so the old state may
        only appear as something that was, and the claim it protected (no Studio
        decision) has to survive the update, because that one is still true."""
        page = " ".join(self.docs().split())
        self.assertIn("Paper Running", page, "the page has not caught up to Studio")
        self.assertNotIn("Studio then showed <strong>Paper Degraded", page,
                         "the page still reports Paper Degraded as the current state")
        self.assertIn("no valid decision recorded", page,
                      "the page dropped the caveat that no Studio decision exists")
        self.assertIn("0.00% is the policy, not an empty account", page,
                      "the page no longer explains what the 0.00% is")
        self.assertAlmostEqual(-29.62 / 2000 * 100, -1.48, places=2)

    def test_both_denominators_are_named_because_the_card_shows_the_other(self):
        """The public GetAgent listing quotes this run on the account basis -
        -0.03% and 0.08% - while the run record quotes the strategy basis,
        -1.48% and 3.76%. Same run, same -29.62 USDT, two denominators.

        A judge who opens the card after reading this page would otherwise find
        two different numbers for one backtest and have no way to tell which
        was the honest one. Both appear here, each named.
        """
        page = " ".join(self.docs().split())
        self.assertIn("account basis", page)
        self.assertIn("0.03%", page)
        self.assertIn("100,000 USDT", page)
        # the two denominators must actually produce the two figures quoted
        net = -29.619686
        self.assertAlmostEqual(net / 2000 * 100, -1.48, places=2)
        self.assertAlmostEqual(net / 100000 * 100, -0.03, places=2)

    def test_the_studio_paper_state_is_stated_not_implied(self):
        """A $10,000 Studio balance at 0.00% next to "paper trading" reads as a
        flat run. It is an empty one, and that is the claim this guards.

        It used to assert the literal string "Paper Degraded", which is a
        transient status - it cleared to Paper Running the next day and took
        this test red with it, for a page that had got *more* accurate. The
        durable property is that the 0.00% is explained, whatever Studio is
        currently reporting.
        """
        page = " ".join(self.docs().split())
        self.assertIn("no valid decision recorded", page)
        self.assertIn("not a Track 2 run log", page)
        # The explanation, not one wording of it. This assertion has now been
        # rewritten twice because it pinned a sentence: first "Paper Degraded",
        # which cleared, then "0.00% is an empty account", which was replaced by
        # a better explanation - the policy only acts on scheduled nights and
        # the next one falls after the deadline. Both times the page had got
        # MORE accurate and the test went red for it.
        self.assertIn("0.00% is the policy, not an empty account", page,
                      "the page no longer explains what the 0.00% is")
        self.assertIn("2026-09-30", page,
                      "the page does not name the next night the Playbook can act on")
        self.assertIn("not a Track 2 run log", page)

    def test_the_two_simulations_are_told_apart(self):
        """One is priced by this project, the other by Bitget's paper portfolio.

        A judge reading "paper trading enabled" beside "fills are simulated"
        would otherwise reasonably assume they are the same venue, and conclude
        either that the platform blessed our arithmetic or that its paper
        account is ours. Neither is true.
        """
        page = " ".join(self.docs().split())
        self.assertIn("two simulations", page)
        self.assertIn("self-reported", page,
                      "the page does not say whose arithmetic prices the fills")
        self.assertIn("Neither has touched real money", page)

    def test_the_reproducibility_claim_names_both_runs(self):
        """Two replays two days apart returned the same curve hash. That is the
        strongest single fact about this backtest and it is worth nothing if
        the page asserts it without naming what can be re-derived."""
        page = " ".join(self.docs().split())
        self.assertIn("096c4d1e", page, "the curve hash is claimed but not shown")
        self.assertIn("two days apart", page)
        self.assertIn("pbrun-60a1da0970b5", page,
                      "the page cites a run the published version did not use")

    def test_the_equity_curve_behind_the_publish_is_named(self):
        """Publishing a backtest_support: full Playbook is gated on a real
        equity curve rather than aggregate metrics alone. Saying the run has
        one, with its point count, is the difference between an auditable
        claim and a number someone could have typed."""
        page = " ".join(self.docs().split())
        self.assertIn("2,121-point equity curve", page)
        self.assertIn("published v0.0.2", page)


class TheOverviewDoesNotCarryTheOneLegNumber(unittest.TestCase):
    """Track 2 scores 50% on quantitative results. The Playbook's -0.76 is a
    one-leg premium, not this product's metric, so it belongs in the docs beside
    its caveat and nowhere a scorer would lift it from."""

    def test_the_landing_page_quotes_no_playbook_figure(self):
        index = " ".join(build_site([])["index.html"].split())
        for figure in ("pbrun-", "-0.76", "\u22120.76", "-1.48", "\u22121.48"):
            self.assertNotIn(figure, index,
                             f"{figure} is a one-leg number on the landing page")


class TheWinRateIsOneNumber(unittest.TestCase):
    """The page said 7/7 in the header tile and "100%, 9 of 9" in the table.

    Same page, same quantity, two answers, and the flattering one was in the
    bigger type. It happened because the header read the graded set and the
    metrics table was handed every row, with nothing tying them together. A
    judge scoring the quantitative half screenshots the tile.

    So the two now come from one computation, and this asserts they agree
    whatever the ledger does next.
    """

    def settled(self):
        from ballast import report
        return report.Site()

    def test_the_header_tile_and_the_metrics_table_agree(self):
        from ballast.metrics import paper_metrics
        rep = self.settled()
        m = paper_metrics(rep.rows, graded=rep.clean)
        self.assertEqual(m["hedges"], len(rep.hedges),
                         "the table grades a different number of hedges than the tile")
        self.assertEqual(m["hedges_that_cut"], rep.shrank,
                         "the table and the tile disagree on how many cut the move")

    def test_hedges_excluded_from_the_grade_are_still_counted_as_orders(self):
        """They were really sent and really moved the book. Dropping them from
        the order count would be hiding activity, not declining to grade it."""
        from ballast.metrics import paper_metrics
        rep = self.settled()
        m = paper_metrics(rep.rows, graded=rep.clean)
        every = [r for r in rep.rows if r.get("action") == "HEDGE"]
        self.assertEqual(m["orders"], len(every))
        self.assertEqual(m["hedges_ungraded"], len(every) - m["hedges"])

    def test_the_return_is_not_quietly_improved_by_the_exclusion(self):
        """Return and drawdown must stay on every row. Removing a bad night
        from a P&L curve because it was our fault is how a record gets
        laundered."""
        from ballast.metrics import paper_metrics
        rep = self.settled()
        graded = paper_metrics(rep.rows, graded=rep.clean)
        whole = paper_metrics(rep.rows)
        for key in ("hedged_total_bp", "unhedged_total_bp",
                    "hedged_max_dd_bp", "unhedged_max_dd_bp", "nights"):
            with self.subTest(key=key):
                self.assertEqual(graded[key], whole[key],
                                 f"{key} changed when hedges were excluded from the grade")

    def test_the_page_says_the_excluded_hedges_exist(self):
        """Quietly grading 7 and printing 7 would be a different dishonesty."""
        from ballast.metrics import paper_metrics
        rep = self.settled()
        m = paper_metrics(rep.rows, graded=rep.clean)
        if not m["hedges_ungraded"]:
            self.skipTest("nothing is currently excluded")
        page = " ".join(rep.paper_metrics_block.split())
        self.assertIn("graded hedges cut the move", page)
        self.assertIn(f"{m['hedges_ungraded']} more were sent", page)
        self.assertIn("defect 3f", page)


class TheSharpeSentenceMatchesTheSharpe(unittest.TestCase):
    """The prose read "both are negative here" while the table beside it showed
    +3.94 and +3.71. A reader who checks one sentence against one number finds
    the page contradicting itself on the metric the track names."""

    def block(self):
        from ballast import report
        return " ".join(report.Site().paper_metrics_block.split())

    def test_the_page_does_not_assert_a_sign_it_does_not_check(self):
        self.assertNotIn("both are negative", self.block())

    def test_the_return_shortfall_is_stated_rather_than_left_in_the_table(self):
        """The hedged book returned less than the untouched one. That is what
        paying for protection looks like, and burying it in a table cell while
        the prose talks about drawdown is the kind of omission a judge reads as
        a claim."""
        from ballast import report
        from ballast.metrics import paper_metrics
        rep = report.Site()
        m = paper_metrics(rep.rows, graded=rep.clean)
        if m["hedged_total_bp"] >= m["unhedged_total_bp"]:
            self.skipTest("the hedged book is not behind on this record")
        self.assertIn("returned less than the book left alone", self.block())


class TheVenueLabelReportsWhatHappened(unittest.TestCase):
    """The night summary said "Bitget Agent Hub, paper-trading" on every night
    since the Hub was wired - including nights that sent no order at all, and
    every night where each order in fact fell back to a simulated fill after
    `HTTP 400: exchange environment is incorrect`.

    Simulated paper is allowed by the track. Calling a 400 and a local fill
    "Agent Hub, paper-trading" is not, and the per-fill rows were already
    honest while the summary above them was not.
    """

    def outcome(self, **kw):
        from ballast.night import _venue_outcome
        base = {"bgc_ok": True, "bgc_why": "bgc 1.x, demo key configured",
                "hedged": 0, "routed": 0, "fell_back": 0, "fallback_reason": ""}
        return _venue_outcome(**{**base, **kw})

    def test_a_night_with_no_orders_claims_no_venue(self):
        out = self.outcome(hedged=0)
        self.assertEqual(out["venue"], "none")
        self.assertEqual(out["orders_sent"], 0)
        self.assertIn("no order was sent", out["venue_detail"])
        self.assertNotIn("Agent Hub, paper-trading", out["venue_detail"])

    def test_orders_that_all_fell_back_are_not_called_agent_hub(self):
        out = self.outcome(hedged=2, fell_back=2,
                           fallback_reason="HTTP 400 from Bitget: exchange "
                                           "environment is incorrect")
        self.assertEqual(out["venue"], "simulated")
        self.assertIn("fell back to a simulated fill", out["venue_detail"])
        self.assertIn("HTTP 400", out["venue_detail"])

    def test_a_genuinely_routed_night_still_says_so(self):
        """The fix must not make the honest case unsayable."""
        out = self.outcome(hedged=2, routed=2)
        self.assertEqual(out["venue"], "bgc-paper")
        self.assertEqual(out["venue_detail"], "Bitget Agent Hub, paper-trading")

    def test_a_mixed_night_names_both_counts(self):
        out = self.outcome(hedged=3, routed=1, fell_back=2,
                           fallback_reason="HTTP 400")
        self.assertEqual(out["venue"], "mixed")
        self.assertIn("1 routed", out["venue_detail"])
        self.assertIn("2 fell back", out["venue_detail"])

    def test_the_page_does_not_repeat_a_venue_the_night_did_not_use(self):
        """Seven committed summaries claim `bgc-paper` on nights where nothing
        was routed. The ledger is append-only and hash-chained, so those rows
        stay exactly as written - correcting a signed record by editing it is
        the one thing this project must never do.

        What can be fixed is the page. It reads the summary, and it must not
        repeat a venue claim for a night with no fill on it.
        """
        from ballast import report
        site = report.Site()
        note = " ".join(site.venue_line.split()) if isinstance(
            site.venue_line, str) else ""
        if not [r for r in site.tonight if r.get("fill")]:
            self.assertIn("no order was sent", note,
                          "the page claims a venue for a night that sent nothing")
            self.assertNotIn("Agent Hub, paper-trading", note)


class TheCrosscheckRowIsReadFromTheFile(unittest.TestCase):
    """This sentence has been wrong four times.

    It said the upstream answered 503 while the file beside it recorded 96
    checked; then it said 96 when the file said 108; then 108 when the file
    said 120. Each needed a human to notice. The fourth was worse than a stale
    count: the upstream renamed its catalog entry, every row came back
    `unknown`, and the hand-typed "116 agree" would have claimed a second
    opinion the project no longer had.

    So the row is rendered from the file, and the states a reader must be able
    to tell apart are each asserted here.
    """

    def row(self, payload):
        from unittest import mock

        from ballast import docs_page
        with mock.patch.object(docs_page, "_crosscheck", return_value=payload):
            return " ".join(docs_page._crosscheck_sentence().split())

    def test_a_run_that_could_check_nothing_says_so(self):
        out = self.row({"counts": {"decisions": 120, "checked": 0, "unknown": 120,
                                   "agreed": 0, "disagreed": 0},
                        "rows": [{"detail": "upstream None: Unknown entry_id"}]})
        self.assertIn("none of the 120 decisions could be", out)
        self.assertIn("120 are recorded", out)
        self.assertIn("Unknown entry_id", out,
                      "the page hides why the second opinion failed")
        self.assertNotIn("agree,", out,
                         "a run that checked nothing must not report agreement")

    def test_a_partial_run_reports_the_unknowns_rather_than_rounding_them_away(self):
        out = self.row({"counts": {"decisions": 120, "checked": 6, "unknown": 114,
                                   "agreed": 6, "disagreed": 0}})
        self.assertIn("All <strong>6</strong> decisions are checked", out)
        self.assertIn("114 recorded unknown", out)
        self.assertIn("6 agree, 0 do not", out)

    def test_a_clean_run_says_nothing_was_unknown(self):
        out = self.row({"counts": {"decisions": 120, "checked": 120, "unknown": 0,
                                   "agreed": 116, "disagreed": 4},
                        "rows": [{"ticker": "ADBE", "session": "2026-09-09",
                                  "bitget_mcp": "no", "agree": False},
                                 {"ticker": "ORCL", "session": "2026-09-10",
                                  "bitget_mcp": "no", "agree": False}]})
        self.assertIn("nothing recorded unknown", out)
        self.assertIn("116 agree, 4 do not", out)
        self.assertIn("ADBE and ORCL", out)

    def test_the_defect_names_appear_only_when_there_is_a_disagreement(self):
        """Claiming an independent source landed on our known defect, on a run
        where nothing disagreed, would be inventing corroboration."""
        out = self.row({"counts": {"decisions": 120, "checked": 120, "unknown": 0,
                                   "agreed": 120, "disagreed": 0}, "rows": []})
        self.assertNotIn("ADBE and ORCL", out)
        self.assertIn("agree on every decision", out)

    def test_different_tickers_produce_different_names(self):
        """Hardcoding ["ADBE", "ORCL"] passes against today's data, because
        today's disagreements happen to be ADBE and ORCL. This feeds rows that
        are not, so a hardcoded list cannot survive.
        """
        out = self.row({"counts": {"decisions": 12, "checked": 12, "unknown": 0,
                                   "agreed": 10, "disagreed": 2},
                        "rows": [{"ticker": "TSLA", "session": "2026-10-28",
                                  "bitget_mcp": "no", "agree": False},
                                 {"ticker": "MU", "session": "2026-09-30",
                                  "bitget_mcp": "no", "agree": False}]})
        self.assertIn("MU", out)
        self.assertIn("TSLA", out)
        self.assertIn("2026-09-30", out)
        self.assertNotIn("ADBE", out)
        self.assertIn("not rows this project had already flagged", out,
                      "an unexpected disagreement was presented as corroboration")

    def test_the_live_page_matches_the_live_file(self):
        import json
        from pathlib import Path as P

        from ballast import docs_page
        counts = json.loads(
            (P(__file__).resolve().parent.parent / "state" /
             "calendar_crosscheck.json").read_text())["counts"]
        out = " ".join(docs_page._crosscheck_sentence().split())
        if counts["checked"]:
            self.assertIn(f"All <strong>{counts['checked']}</strong> decisions", out)
            self.assertIn(f"{counts['agreed']} agree, {counts['disagreed']} do not", out)
        else:
            self.assertIn("could not be checked", out.replace(
                "could be checked", "could not be checked"))


class TheGiveUpRuleTellsDownFromFlaky(unittest.TestCase):
    """A run that checked six tickers then met five 404s in a row abandoned the
    remaining 109 and published 114 unknown - for a service that was working.
    The rule was written for an outage and applied to a flaky upstream."""

    def test_a_dead_upstream_still_costs_only_three_calls(self):
        from ballast.crosscheck import GIVE_UP_AFTER, _give_up
        self.assertTrue(_give_up(GIVE_UP_AFTER, 0, GIVE_UP_AFTER, 120))
        self.assertFalse(_give_up(GIVE_UP_AFTER - 1, 0, GIVE_UP_AFTER - 1, 120))

    def test_a_flaky_upstream_does_not_abandon_the_run(self):
        from ballast.crosscheck import _give_up
        self.assertFalse(_give_up(5, 6, 5, 120),
                         "five failures after six answers stopped a working run")

    def test_a_genuinely_degraded_run_still_exits(self):
        from ballast.crosscheck import _give_up
        self.assertTrue(_give_up(2, 6, 40, 120),
                        "a third of the rows failing should still stop the run")

    def test_the_calendar_entry_is_resolved_from_the_catalog_not_pinned(self):
        """The upstream renamed this entry and every row came back
        `Unknown entry_id`. A pinned id is a silent single point of failure,
        so the second opinion asks the catalog what the entry is called."""
        from unittest import mock

        from ballast import crosscheck
        crosscheck._ENTRY_CACHE[0] = None
        with mock.patch.object(crosscheck.mcp, "catalog",
                               return_value={"entries": [{"id": "equity_calendar"}]}):
            self.assertEqual(crosscheck.calendar_entry(), "equity_calendar")
        crosscheck._ENTRY_CACHE[0] = None
        with mock.patch.object(crosscheck.mcp, "catalog",
                               return_value={"entries": [
                                   {"id": "equity_calendar_earnings"}]}):
            self.assertEqual(crosscheck.calendar_entry(), "equity_calendar_earnings")
        crosscheck._ENTRY_CACHE[0] = None

    def test_the_second_opinion_queries_whatever_the_catalog_named(self):
        """The query must use the resolved id. Pinning it back inside
        second_opinion would leave calendar_entry() correct and unused."""
        import datetime as dt
        from unittest import mock

        from ballast import crosscheck
        seen = {}

        def spy(entry_id, **params):
            seen["entry"] = entry_id
            return {"results": []}

        crosscheck._ENTRY_CACHE[0] = None
        with mock.patch.object(crosscheck.mcp, "catalog",
                               return_value={"entries": [{"id": "equity_calendar"}]}), \
             mock.patch.object(crosscheck.mcp, "query", side_effect=spy):
            crosscheck.second_opinion("ADBE", dt.date(2026, 9, 10), {})
        crosscheck._ENTRY_CACHE[0] = None
        self.assertEqual(seen.get("entry"), "equity_calendar",
                         "second_opinion ignored the resolved entry id")
