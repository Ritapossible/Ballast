"""docs/SUBMISSION.md is the document the judges weight most heavily, and it was the
last file in the repo still quoting measured figures as literals.

It said "699 live rTokens, 219 have a matched stock perpetual" and "480 of 699 have
no perp leg" - the universe measured when the file was written. facts.json had said
1,173 and 241 for days. The same drift the README generator exists to prevent, in
the one file a judge actually reads end to end.

The prose here is argued, not tabular, so it is not generated. It is checked: every
figure below must agree with docs/facts.json, and the test names the sentence to fix
when it does not.
"""
from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ballast import facts

SUBMISSION = Path(__file__).resolve().parent.parent / "docs" / "SUBMISSION.md"

# The document writes ranges with an en dash, so the test has to match one. Spelled
# as an escape because a literal en dash in source is what RUF001 exists to catch.
EN_DASH = "\u2013"


class SubmissionFigures(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = SUBMISSION.read_text()
        cls.f = facts.load()

    def test_hedgeable_universe_matches_facts(self) -> None:
        total, hedgeable = self.f["rtokens_total"], self.f["rtokens_hedgeable"]
        self.assertIn(
            f"Of {total:,} live rTokens, **{hedgeable:,} have a matched stock perpetual**",
            self.text,
            "part 1 quotes a stale universe; facts.json says "
            f"{hedgeable:,} of {total:,}",
        )

    def test_unhedgeable_complement_matches_facts(self) -> None:
        total, hedgeable = self.f["rtokens_total"], self.f["rtokens_hedgeable"]
        self.assertIn(
            f"**{total - hedgeable:,} of {total:,} rTokens have no perp leg.**",
            self.text,
            "part 2 states what Ballast cannot protect; that count is the "
            "complement of the hedgeable universe and must follow it",
        )

    def test_no_superseded_universe_anywhere(self) -> None:
        """The pre-drift numbers must not survive in a sentence we did not check."""
        stale = {facts.DEFAULTS["rtokens_total"], facts.DEFAULTS["rtokens_hedgeable"]}
        live = {self.f["rtokens_total"], self.f["rtokens_hedgeable"]}
        for n in stale - live:
            self.assertNotIn(
                str(n), self.text,
                f"{n} is the superseded universe count and is still in the file",
            )

    def test_median_variance_removed_matches_facts(self) -> None:
        pct = f"{self.f['median_r2'] * 100:.1f}%"
        self.assertIn(f"**median {pct}", self.text, "part 1 median R2 is stale")
        self.assertIn(
            f"| Median overnight variance removed | **{pct}** |", self.text,
            "the part 3 metrics table disagrees with facts.json",
        )

    def test_tail_reduction_matches_facts(self) -> None:
        pct = self.f["median_tail_cut_pct"]
        self.assertIn(f"| Median p95 tail reduction | **{pct}%** |", self.text)
        self.assertIn(f"median **{pct}% off the p95 tail**", self.text)

    def test_costs_match_facts(self) -> None:
        self.assertIn(f"**{self.f['hedge_cost_bp']} bp**", self.text)
        self.assertIn(f"**{self.f['exit_cost_bp']:.0f} bp**", self.text)

    def test_night_range_matches_the_measured_sample(self) -> None:
        oos = self.f["oos"]
        span = f"{oos['shortest']}{EN_DASH}{oos['longest']}"
        found = set(re.findall(rf"\b(\d{{2,3}}{EN_DASH}\d{{2,3}}) "
                               rf"(?:overnight windows|nights each)", self.text))
        self.assertTrue(found, "part 1 and part 3 must state the sample length")
        self.assertEqual(
            found, {span},
            f"the sample runs {span} nights; the file says {sorted(found)}",
        )

    def test_track_and_subtheme_are_stated(self) -> None:
        self.assertIn("| **Track** | Agentic Trading |", self.text)
        self.assertIn("| **Sub-theme** | Event-Driven Agent |", self.text)


if __name__ == "__main__":
    unittest.main()


class BetaFigures(unittest.TestCase):
    """The last measured literal in the repo, and the quietest way one goes stale.

    SUBMISSION.md claimed a hedge ratio of 0.985-1.040 and "within 4% of 1.00".
    Nothing regenerated either, so both drifted as the sample grew: the measured
    range was 0.992-1.027, which is TIGHTER. The claim stayed true while the
    measurement got better - so no check that only asked "is this still correct?"
    would ever have fired.
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls.text = SUBMISSION.read_text()
        cls.f = facts.load()

    def test_range_matches_the_measurement(self) -> None:
        f = self.f
        self.assertIn(
            f"| Hedge ratio \u03b2 | {f['beta_min']:.3f}{EN_DASH}{f['beta_max']:.3f} "
            f"({f['beta_names']} names) |",
            self.text, "the part 3 beta range disagrees with facts.json")

    def test_tolerance_claim_is_derived_not_asserted(self) -> None:
        pct = facts.beta_within_pct(self.f)
        self.assertIn(f"β within {pct}% of 1.00", self.text)

    def test_the_tolerance_actually_bounds_both_ends(self) -> None:
        """The claim must hold for the worst name, not just on average."""
        pct = facts.beta_within_pct(self.f)
        for edge in (self.f["beta_min"], self.f["beta_max"]):
            self.assertLessEqual(abs(edge - 1.0) * 100, pct)


class SuiteCountsInTheProse(unittest.TestCase):
    """Every count about this repo, checked against the repo.

    `report._red_team_count` was added because the evidence page claimed 18
    red-team tests against a file holding 25. The lesson was applied in exactly one
    place: the evidence page still said "Eighteen" in prose, the docs page said
    "18", and this document claimed 79 tests in one sentence and 103 in another
    while the suite held 347. A number nobody generates is a number nobody rereads.
    """

    @classmethod
    def setUpClass(cls) -> None:
        from ballast import suite
        cls.text = SUBMISSION.read_text()
        cls.suite = suite

    def test_the_red_team_count_is_current(self) -> None:
        n = self.suite.red_team()
        self.assertIn(f"**{n} red-team tests**", self.text,
                      f"tests/test_enforcer.py holds {n} tests")

    def test_the_suite_size_is_current(self) -> None:
        n = self.suite.total()
        self.assertIn(f"**{n} tests, network-free", self.text,
                      f"tests/ holds {n} tests")

    def test_the_deliverables_row_is_current(self) -> None:
        n, e2e = self.suite.total(), self.suite.end_to_end()
        self.assertIn(f"- {n}, network-free, incl. {e2e} end-to-end |", self.text,
                      f"tests/ holds {n}, of which {e2e} are end-to-end")

    def test_no_superseded_suite_size_survives_anywhere(self) -> None:
        """The exact strings that went stale, so they cannot come back."""
        for dead in ("79 tests", "103, network-free", "17 end-to-end",
                     "18 red-team tests"):
            self.assertNotIn(dead, self.text, f"stale count: {dead}")

    def test_the_published_pages_show_the_current_count(self) -> None:
        """Checked in the rendered output, which is what a reader actually sees.

        Asserting against the source would fail on the docstring that records the
        original defect - the history has to stay readable, the rendered page has
        to stay true.
        """
        import tempfile
        from unittest import mock

        from ballast import config, docs_page, report
        from ballast.ledger import Ledger

        n = self.suite.red_team()
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "ledger.jsonl"
            Ledger(path, b"t").append("night_summary", {"session": "2026-09-10"})
            with mock.patch.object(config, "LEDGER_PATH", path), \
                 mock.patch.object(config, "secret", return_value=b"t"), \
                 mock.patch.object(config, "STATE", Path(d)), \
                 mock.patch.object(report, "OUT_DIR", Path(d)), \
                 mock.patch.object(docs_page, "OUT", Path(d) / "docs.html"):
                pages = {pg.name: pg.read_text() for pg in report.build()}
                pages["docs.html"] = docs_page.build().read_text()

        # The claim sentence, which both pages share. Matched on its own rather
        # than on the bare number: the defects section quotes the original wrong
        # figure on purpose, and that disclosure has to keep rendering.
        claim = re.compile(r"(\d+) red-team tests drive hostile intents")
        for name in ("evidence.html", "docs.html"):
            found = claim.findall(re.sub(r"<[^>]+>", "", pages[name]))
            self.assertEqual(found, [str(n)],
                             f"{name} claims {found} red-team tests; the file holds {n}")


class TheCountMatchesTheCommand(unittest.TestCase):
    """SUBMISSION.md prints a command beside the number it claims.

    Counting the bare substring "def test_" reported 352 against a suite unittest
    discovers as 351, because a test asserting on that substring contains it. A
    judge who runs the command printed in the deliverables table must see the
    number printed next to it.
    """

    def test_the_counted_total_is_what_the_loader_discovers(self) -> None:
        import unittest as ut

        from ballast import suite
        found = ut.defaultTestLoader.discover(str(SUBMISSION.parent.parent / "tests"))

        def walk(s) -> int:
            return (sum(walk(x) for x in s)
                    if isinstance(s, ut.TestSuite) else 1)

        self.assertEqual(suite.total(), walk(found),
                         "the suite size in SUBMISSION.md would not match "
                         "`python3 -m unittest discover -s tests`")
