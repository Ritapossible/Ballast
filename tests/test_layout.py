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
             mock.patch.object(config, "STATE", Path(d)), \
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
        """Two sticky bars with a hardcoded offset overlap when the header wraps.

        The markup moved - the nav now sits inside the brand row so a desktop
        gets one bar instead of two - so this asserts the property rather than
        the old shape: exactly one sticky container, and the nav inside it.
        """
        for name, html in self.each():
            self.assertEqual(html.count('class="chrome"'), 1, name)
            chrome = re.search(r'<div class="chrome">(.*?)</header></div>',
                               html, re.S)
            self.assertIsNotNone(chrome, name)
            self.assertIn('class="nav"', chrome.group(1), name)
            self.assertIn('class="brand"', chrome.group(1), name)
            self.assertNotIn("top:57px", html, name)

    def test_the_header_is_one_row_on_a_desktop_and_two_on_a_phone(self):
        """Brand, six sections and an action do not share a line at 390px.

        The phone arrangement - nav on its own full-width scrolling strip
        below the brand - is the only one that fits six sections, so the
        single-row desktop header has to hand it back below a breakpoint.
        """
        for name, html in self.each():
            self.assertIn("@media(max-width:900px)", html, name)
            rule = re.search(r"@media\(max-width:900px\)\{(.*?)\n\}", html, re.S)
            self.assertIsNotNone(rule, name)
            body = rule.group(1)
            self.assertIn("flex-basis:100%", body,
                          f"{name}: the nav does not take its own row")
            self.assertIn(".nav{order:3", body,
                          f"{name}: the nav does not drop below the brand")

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
        expected = {"index.html", "tonight.html", "settled.html", "reader.html",
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
                    "settled.html": "Settled", "reader.html": "Reader",
                    "evidence.html": "Evidence", "docs.html": "Docs"}
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
            for forbidden in ("http://", "cdn.", "fonts.googleapis", "@import"):
                self.assertNotIn(forbidden, html, f"{name} pulls in {forbidden}")

    def test_every_script_is_a_local_file(self):
        """The coverage lookup added the site's first script, so this replaced a
        blanket ban on `<script`. The CSP is `script-src 'self'` with no
        'unsafe-inline', so an inline block would silently not run and an
        off-origin src would be refused - both must fail here instead."""
        for name, html in self.each():
            for tag in re.findall(r"<script\b[^>]*>", html):
                src = re.search(r'src="([^"]+)"', tag)
                self.assertIsNotNone(src, f"{name} has an inline script: {tag}")
                self.assertNotRegex(src.group(1), r"^(?:[a-z]+:)?//",
                                    f"{name} loads a script off-origin: {tag}")


if __name__ == "__main__":
    unittest.main()


class DeadSpaceCase(unittest.TestCase):
    """A hero section and the content section beneath it stacked their padding,
    and the table added its own top margin on top: 159px of empty screen above
    the first row on a phone, pushing the thing the page exists to show down.
    Measured before and after in a real browser; 159px became 103px."""

    @classmethod
    def setUpClass(cls):
        cls.pages = build_pages()

    def test_the_block_after_a_hero_is_tightened_on_a_phone(self):
        for name, html in self.pages.items():
            self.assertIn(".bd + section{padding-top:30px}", html, name)
            self.assertIn(".wrap > .scroll:first-child{margin-top:0}", html, name)

class VerticalRhythmFollowsTheViewportHeight(unittest.TestCase):
    """The layout was responsive in width only.

    `section{padding:88px 0}` is fine on a tall monitor and overridden on a
    phone, but a 1366x700 laptop - the most common judging screen there is -
    met a 1041px hero on the landing page and a documentation page whose whole
    first screen was a heading. Nothing overflowed; there was simply nothing
    to read without scrolling.
    """

    def css(self) -> str:
        from ballast.theme import CSS
        return CSS

    def test_section_padding_scales_with_viewport_height(self):
        rule = re.search(r"\bsection\{padding:([^;]+);", self.css())
        self.assertIsNotNone(rule, "section padding rule not found")
        value = rule.group(1)
        self.assertIn("vh", value,
                      f"section padding {value!r} ignores viewport height")
        self.assertIn("clamp", value,
                      "an unclamped vh collapses the rhythm on a short window")

    def test_the_clamp_still_bottoms_out_somewhere_readable(self):
        """A floor near zero would jam the sections together on a netbook."""
        rule = re.search(r"\bsection\{padding:clamp\((\d+)px,([\d.]+)vh,(\d+)px\)",
                         self.css())
        self.assertIsNotNone(rule, "expected clamp(min,vh,max) on section padding")
        low, _, high = (float(g) for g in rule.groups())
        self.assertGreaterEqual(low, 40, "floor too tight to breathe")
        self.assertLessEqual(low, high, "clamp floor above its ceiling")
        self.assertLessEqual(high, 96, "ceiling taller than the old fixed value")

    def test_the_phone_override_still_wins(self):
        """The 640px rule comes later in the cascade and must stay, or this
        change would quietly re-space every phone screen too."""
        css = self.css()
        self.assertLess(css.index("section{padding:clamp"),
                        css.index("@media(max-width:640px)"),
                        "the phone override no longer follows the base rule")
        tail = css[css.index("@media(max-width:640px)"):]
        self.assertIn("section{padding:56px 0}", tail)

class TheFooterIsCentredAndCarriesTheMark(unittest.TestCase):
    """It was a left-aligned run-on sentence under a centred page.

    The footer holds the only source link on every page, so it is the one
    piece of chrome a reader goes looking for. It gets the mark and the
    middle of the column.
    """

    @classmethod
    def setUpClass(cls):
        cls.pages = build_pages()

    def test_every_page_centres_its_footer(self):
        for name, html in self.pages.items():
            self.assertIn(".foot{text-align:center", html, name)
            self.assertIn('class="wrap foot"', html, name)

    def test_the_mark_is_in_the_footer_on_every_page(self):
        for name, html in self.pages.items():
            foot = html[html.index("<footer"):]
            self.assertIn("foot-brand", foot, name)
            self.assertIn("<svg", foot, f"{name}: the footer brand has no mark")

    def test_the_source_link_survived_the_rearrangement(self):
        """The footer is the only place the repository is linked from."""
        for name, html in self.pages.items():
            foot = html[html.index("<footer"):]
            self.assertIn("github.com", foot, name)
            self.assertIn(">source<", foot, name)

    def test_it_still_says_what_the_ledger_is_not(self):
        for name, html in self.pages.items():
            foot = html[html.index("<footer"):]
            self.assertIn("paper trading only", foot, name)
            self.assertIn("not financial advice", foot, name)

