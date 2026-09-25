"""The two drafts that leave the repo and cannot be corrected afterwards.

docs/SUBMISSION.md has been checked against facts.json since the universe drifted
under it. The X drafts were not, and drifted the same way: X_POST.md still offered
"226 of 2,125 rTokens" to paste into a tweet while facts.json said 235 of 2,587 and
the article next to it said 2,587. A post cannot be edited after it is sent, so the
draft is the one file where a stale figure is permanent.

X_ARTICLE.md also quoted "93 decided by the model, 39 by the rule". 93 is the number
of model answers that passed the gates - but 7 of those were abstentions, which hand
the night back to the rule. The ledger's own `decided_by` says 86 and 46, which is
what the site renders. Counting acceptances and calling them decisions is a mistake
no proofread catches, so it is checked here against the chain.
"""
from __future__ import annotations

import json
import re
import sys
import unittest
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ballast import facts

DOCS = Path(__file__).resolve().parent.parent / "docs"
LEDGER = Path(__file__).resolve().parent.parent / "state" / "ledger.jsonl"
DRAFTS = ("X_POST.md", "X_ARTICLE.md")


def _decisions() -> list[dict]:
    if not LEDGER.exists():
        return []
    return [json.loads(line)["body"] for line in LEDGER.read_text().splitlines()
            if line.strip() and json.loads(line).get("kind") == "decision"]


class DraftUniverse(unittest.TestCase):
    """Both drafts quote the hedgeable universe; both must quote the live one."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.f = facts.load()
        cls.text = {name: (DOCS / name).read_text() for name in DRAFTS}

    def test_both_figures_are_stated_and_current(self) -> None:
        """Phrasing differs between the drafts, so check the numbers, not a sentence."""
        total, hedgeable = self.f["rtokens_total"], self.f["rtokens_hedgeable"]
        for name, text in self.text.items():
            self.assertIn(f"{total:,}", text,
                          f"{name} no longer states the size of the universe")
            self.assertIn(str(hedgeable), text,
                          f"{name} no longer states how much of it is hedgeable")

    def test_no_other_universe_sized_number_is_quoted(self) -> None:
        """Any other thousands-scale count in these drafts is a universe gone stale."""
        total = self.f["rtokens_total"]
        for name, text in self.text.items():
            quoted = set(re.findall(r"\b\d{1,3},\d{3}\b", text))
            self.assertEqual(
                quoted, {f"{total:,}"},
                f"{name} quotes {sorted(quoted - {f'{total:,}'})}; the live "
                f"universe is {total:,}",
            )

    def test_no_superseded_count_survives_anywhere(self) -> None:
        live = {self.f["rtokens_total"], self.f["rtokens_hedgeable"]}
        stale = {facts.DEFAULTS["rtokens_total"],
                 facts.DEFAULTS["rtokens_hedgeable"]} - live
        for name, text in self.text.items():
            for n in stale:
                self.assertNotIn(f"{n:,}", text,
                                 f"{n:,} is a superseded count still in {name}")


class ArticleDecisionSplit(unittest.TestCase):
    """The split must come from `decided_by`, not from who answered."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.text = (DOCS / "X_ARTICLE.md").read_text()
        cls.dec = _decisions()

    def setUp(self) -> None:
        if not self.dec:
            self.skipTest("no ledger in this checkout")

    def test_split_matches_the_chain(self) -> None:
        by = Counter(d["inputs"].get("decided_by") for d in self.dec)
        self.assertIn(
            f"Over {len(self.dec)} decisions on the live chain: "
            f"**{by['model']} decided by the model, {by['rule']} by the rule**.",
            self.text,
            f"the chain says {by['model']} model / {by['rule']} rule "
            f"over {len(self.dec)} decisions",
        )

    def test_the_stated_reasons_account_for_every_rule_night(self) -> None:
        """Each number in the breakdown is a real count, and they leave nothing over."""
        by = Counter(d["inputs"].get("decided_by") for d in self.dec)
        why = Counter(d.get("reader", {}).get("rejected_because")
                      for d in self.dec
                      if d["inputs"].get("decided_by") == "rule")
        abstained = why.pop(None, 0)
        stated = {
            "quote_not_in_sources": r"\*\*(\d+) answers for quoting a headline",
            "schema_violation": r"and (\d+) for schema violations",
            "model_unavailable": r"took over on (\d+) nights",
        }
        for reason, pattern in stated.items():
            found = re.search(pattern, self.text)
            self.assertIsNotNone(found, f"the article no longer states {reason}")
            self.assertEqual(int(found.group(1)), why[reason],
                             f"{reason} happened {why[reason]} times")
        found = re.search(r"remaining (\d+) the model answered cleanly", self.text)
        self.assertIsNotNone(found, "the article must account for the abstentions")
        self.assertEqual(int(found.group(1)), abstained,
                         f"the model abstained on {abstained} nights")
        self.assertEqual(sum(why.values()) + abstained, by["rule"],
                         "the stated reasons must exhaust the rule-decided nights")


if __name__ == "__main__":
    unittest.main()
