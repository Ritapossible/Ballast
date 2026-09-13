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
