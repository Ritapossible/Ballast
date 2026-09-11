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
    """Render every public page against a throwaway ledger."""
    with tempfile.TemporaryDirectory() as d:
        ledger_path = Path(d) / "ledger.jsonl"
        Ledger(ledger_path, b"t").append("night_summary", {"session": "2026-09-10"})
        with mock.patch.object(config, "LEDGER_PATH", ledger_path), \
             mock.patch.object(config, "secret", return_value=b"t"), \
             mock.patch.object(report, "OUT_DIR", Path(d)), \
             mock.patch.object(docs_page, "OUT", Path(d) / "docs.html"):
            pages = {pg.name: pg.read_text() for pg in report.build()}
            pages["docs.html"] = docs_page.build().read_text()
            return pages


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
        """Clip at the root, not on body: overflow on body breaks position:sticky."""
        for name, html in self.each():
            self.assertIn("html{overflow-x:clip}", html, name)
            self.assertNotIn("body{overflow-x", html, name)
            self.assertIn("img,svg,table,pre{max-width:100%}", html, name)
            self.assertIn(".wrap,.narrow,.docs,.prose{min-width:0}", html, name)

    def test_anchors_clear_the_sticky_header(self):
        for name, html in self.each():
            self.assertIn("scroll-margin-top", html, name)

    def test_wide_content_scrolls_inside_its_own_container(self):
        """Tables have a min-width; they must sit in a scroller, not widen the page."""
        for name, html in self.each():
            if "<table" in html:
                self.assertRegex(html, r'class="scroll\b', name)
                self.assertIn("overflow-x:auto", html, name)

    def test_every_table_stacks_on_a_phone(self):
        """A 560px table on a 400px screen parks its last column off-screen while
        that column's text still sets the row height - which is how the Tonight
        page came to show 450px-tall rows, blank below the first two cells. Every
        table stacks instead, and every cell carries the label it stacks under."""
        for name, html in self.each():
            for wrapper in re.findall(r'<div class="scroll([^"]*)"><table', html):
                self.assertIn("stacked", wrapper, f"{name}: a table does not stack")
            for row in re.findall(r"<tr>(?!<th)(.*?)</tr>", html):
                if "<td" not in row:
                    continue
                cells = re.findall(r"<td[^>]*>", row)
                unlabelled = [c for c in cells if "data-label=" not in c]
                self.assertEqual(unlabelled, [], f"{name}: cells without a label {unlabelled}")

    def test_no_capital_sigma_reaches_a_page(self):
        """Labels are uppercased in CSS, and Greek σ uppercases to Σ - summation,
        not standard deviation. On a page quoting 1-sigma moves that is the wrong
        symbol, and it was wrong on desktop too."""
        for name, html in self.each():
            self.assertNotIn("\u03a3", html, f"{name}: capital sigma")

    def test_no_unrounded_float_is_displayed(self):
        """The ledger is append-only, so a rationale written before the policy fix
        keeps 11.291999999999998bp for good. The page rounds what it renders; the
        signed record is untouched."""
        for name, html in self.each():
            body = re.sub(r"<style>.*?</style>", "", html, flags=re.S)
            self.assertEqual(re.findall(r"\d+\.\d{4,}", body), [], name)

    def test_the_stacked_rules_are_present(self):
        for name, html in self.each():
            if "<table" in html:
                self.assertIn("@media(max-width:720px)", html, name)
                self.assertIn("content:attr(data-label)", html, name)

    def test_every_in_page_anchor_resolves(self):
        for name, html in self.each():
            ids = set(re.findall(r'id="([^"]+)"', html))
            dead = [a for a in re.findall(r'href="#([^"]+)"', html)
                    if a not in ids and a != "top"]
            self.assertEqual(dead, [], f"{name}: dead anchors {dead}")

    def test_every_page_links_to_every_other(self):
        """The nav is the only way around a multi-page site; it must be complete."""
        expected = {"index.html", "tonight.html", "settled.html",
                    "evidence.html", "docs.html"}
        for name, html in self.each():
            for target in expected - {name}:
                self.assertIn(f'href="{target}"', html, f"{name} cannot reach {target}")

    def test_exactly_one_nav_item_is_marked_active_per_page(self):
        """The underline must follow the page, not sit on Overview everywhere."""
        for name, html in self.each():
            active = html.count('class="on"')
            self.assertEqual(active, 1, f"{name} has {active} active nav items")

    def test_the_active_item_matches_the_page(self):
        expected = {"index.html": "Overview", "tonight.html": "Tonight",
                    "settled.html": "Settled", "evidence.html": "Evidence",
                    "docs.html": "Docs"}
        for name, html in self.each():
            self.assertIn(f'class="on" href="{name}">{expected[name]}</a>', html, name)

    def test_the_header_button_leaves_the_landing_page(self):
        self.assertIn('class="btn btn-p" href="tonight.html"', self.pages["index.html"])

    def test_no_negative_margins_that_widen_the_document(self):
        """A bled-to-edge element widened the page and broke every sticky bar."""
        for name, html in self.each():
            self.assertNotIn("margin:0 -18px", html, name)
            self.assertIn("overflow-x:clip", html, name)

    def test_no_external_resources(self):
        for name, html in self.each():
            for forbidden in ("<script", "http://", "cdn.", "fonts.googleapis", "@import"):
                self.assertNotIn(forbidden, html, f"{name} pulls in {forbidden}")


if __name__ == "__main__":
    unittest.main()
