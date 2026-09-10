"""Structural guards for both public pages.

CSS cannot be unit-tested, but the mistakes that actually broke this site on a
phone are all structural and can be: two independently sticky bars that overlapped
once the header wrapped, and a bullet list whose flex items turned every inline
<strong> into a column. Each check below corresponds to a bug that shipped.
"""
from __future__ import annotations

import re
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from ballast import config, docs_page, report
from ballast.ledger import Ledger


def build_pages() -> dict[str, str]:
    with tempfile.TemporaryDirectory() as d:
        ledger_path = Path(d) / "ledger.jsonl"
        Ledger(ledger_path, b"t").append("night_summary", {"session": "2026-09-10"})
        with mock.patch.object(config, "LEDGER_PATH", ledger_path), \
             mock.patch.object(config, "secret", return_value=b"t"), \
             mock.patch.object(report, "OUT", Path(d) / "index.html"), \
             mock.patch.object(docs_page, "OUT", Path(d) / "docs.html"):
            return {"index": report.build().read_text(),
                    "docs": docs_page.build().read_text()}


class TestLayout(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pages = build_pages()

    def each(self):
        return self.pages.items()

    def test_declares_a_viewport(self):
        for name, html in self.each():
            self.assertIn('name="viewport"', html, name)

    def test_header_and_nav_share_one_sticky_container(self):
        """Two sticky bars with a hardcoded offset overlap when the header wraps."""
        for name, html in self.each():
            self.assertEqual(html.count('class="chrome"'), 1, name)
            self.assertIsNotNone(
                re.search(r'<div class="chrome">.*?</nav></div>', html, re.S), name)
            self.assertNotIn("top:57px", html, name)

    def test_bullets_do_not_use_flex(self):
        """Flex made every inline <strong> a column; the marker is absolute now."""
        for name, html in self.each():
            self.assertIn(".bul li{position:relative", html, name)
            self.assertNotIn(".bul li{display:flex", html, name)

    def test_guards_against_horizontal_overflow(self):
        for name, html in self.each():
            self.assertIn("overflow-x:hidden", html, name)
            self.assertIn("img,svg,table,pre{max-width:100%}", html, name)

    def test_anchors_clear_the_sticky_header(self):
        for name, html in self.each():
            self.assertIn("scroll-margin-top", html, name)

    def test_wide_content_scrolls_inside_its_own_container(self):
        """Tables have a min-width; they must sit in a scroller, not widen the page."""
        for name, html in self.each():
            if "<table" in html:
                self.assertIn('class="scroll"', html, name)
                self.assertIn("overflow-x:auto", html, name)

    def test_every_in_page_anchor_resolves(self):
        for name, html in self.each():
            ids = set(re.findall(r'id="([^"]+)"', html))
            dead = [a for a in re.findall(r'href="#([^"]+)"', html)
                    if a not in ids and a != "top"]
            self.assertEqual(dead, [], f"{name}: dead anchors {dead}")

    def test_pages_link_to_each_other(self):
        self.assertIn('href="docs.html"', self.pages["index"])
        self.assertIn('href="index.html', self.pages["docs"])

    def test_no_external_resources(self):
        for name, html in self.each():
            for forbidden in ("<script", "http://", "cdn.", "fonts.googleapis", "@import"):
                self.assertNotIn(forbidden, html, f"{name} pulls in {forbidden}")


if __name__ == "__main__":
    unittest.main()
