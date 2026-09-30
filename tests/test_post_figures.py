"""The X drafts are checked by tools/check_post.py, not by this suite.

This file used to pin the drafts' figures to the chain, the paper metrics and
facts.json. Those move every night, so every nightly ledger commit turned CI red
for drafts nobody had touched - the suite went red on a schedule, which teaches
everyone to ignore it. The value checks now live in a command run in the minute
before posting.

What stays here is what rots silently: the checker reads the drafts by regex,
so a reworded sentence turns it into a script that reports success having
compared nothing. The values are deliberately not pinned; the parsing is.
"""
from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def _checker():
    spec = importlib.util.spec_from_file_location(
        "check_post", ROOT / "tools" / "check_post.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ThePrePostCheckerStillReadsTheDrafts(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.checker = _checker()
        cls.texts = {name: (ROOT / "docs" / name).read_text()
                     for name in ("X_ARTICLE.md", "X_POST.md")}

    def test_every_figure_is_still_found(self) -> None:
        rows = self.checker.expectations()
        self.assertGreaterEqual(len(rows), 25,
                                "the checker stopped deriving most of its figures")
        for file, what, patterns, expected in rows:
            if expected == "<none>":
                continue
            with self.subTest(figure=what):
                self.assertTrue(
                    self.checker.matches(self.texts[file], patterns),
                    f"no pattern for {what!r} matches {file} any more, so it is "
                    f"no longer being checked")

    def test_a_wrapped_figure_is_still_seen(self) -> None:
        """Markdown wraps at the margin; a figure split across lines still counts."""
        found = self.checker.matches("Over 12\ndecisions on the live chain",
                                     [r"Over (\d+) decisions on the live chain"])
        self.assertEqual(found, ["12"])

    def test_an_outage_forbids_an_agreement_count(self) -> None:
        """Fail-closed: when the second opinion is down, the last good number
        must not be quoted as though it still held."""
        from unittest import mock
        real = self.checker.json.loads

        def down(text, *a, **k):
            data = real(text, *a, **k)
            if isinstance(data, dict) and "counts" in data and "rows" in data:
                data = dict(data, counts={"decisions": 5, "checked": 0, "agreed": 0,
                                          "disagreed": 0, "unknown": 5})
            return data

        with mock.patch.object(self.checker.json, "loads", side_effect=down):
            rows = self.checker.expectations()
        forbidden = [r for r in rows if r[3] == "<none>"]
        self.assertEqual(len(forbidden), 1)
        self.assertTrue(self.checker.matches(self.texts[forbidden[0][0]],
                                             forbidden[0][2]),
                        "the article quotes an agreement count, and the checker "
                        "must flag it while the service is down")


if __name__ == "__main__":
    unittest.main()
