"""The tail chart is the one visual claim on the site, so its inputs are pinned.

Colours are not a matter of taste here: the site's cyan and rose sit at OKLCH
L 0.81 and 0.72, outside the 0.48-0.67 band a dark surface needs. These are the
same hues stepped into the band and validated - CVD deltaE 11.9 deutan, 29.0
normal-vision, both over 3:1 on the chart surface.
"""
from __future__ import annotations

import re
import unittest

from ballast import report

ROWS = [
    {"name": "SPY", "nights": 143, "p95_unhedged": 131, "p95_hedged": 18},
    {"name": "AMD", "nights": 100, "p95_unhedged": 766, "p95_hedged": 29},
    {"name": "COIN", "nights": 258, "p95_unhedged": 655, "p95_hedged": 66},
]


class TailChartCase(unittest.TestCase):
    def test_one_row_per_name(self):
        svg = report._tail_chart(ROWS)
        self.assertEqual(len(re.findall(r"<line [^>]*stroke-width=\"2\"", svg)), len(ROWS))

    def test_rows_are_ordered_by_the_tail_they_remove(self):
        names = re.findall(r"text-anchor=\"end\"[^>]*>([A-Z]+)<", report._tail_chart(ROWS))
        self.assertEqual(names, ["AMD", "COIN", "SPY"])

    def test_both_values_are_labelled_on_every_row(self):
        svg = report._tail_chart(ROWS)
        for row in ROWS:
            self.assertIn(f"{row['p95_unhedged']:,} &#8594; {row['p95_hedged']:,}", svg)

    def test_it_carries_no_script(self):
        """The page loads no JavaScript at all - that is what lets the CSP be
        default-src 'none'. A chart that needs a script would break the claim."""
        svg = report._tail_chart(ROWS)
        for forbidden in ("<script", "onload=", "onclick=", "href=", "url("):
            self.assertNotIn(forbidden, svg)

    def test_the_validated_colours_are_the_ones_used(self):
        svg = report._tail_chart(ROWS)
        self.assertIn(report.TAIL_UNHEDGED, svg)
        self.assertIn(report.TAIL_HEDGED, svg)
        self.assertNotIn("#00d9ec", svg)     # the unvalidated site accent
        self.assertNotIn("#fb7185", svg)

    def test_a_legend_names_both_series(self):
        svg = report._tail_chart(ROWS)
        self.assertIn("p95 unhedged", svg)
        self.assertIn("p95 hedged", svg)

    def test_it_is_described_for_a_screen_reader(self):
        svg = report._tail_chart(ROWS)
        self.assertIn('role="img"', svg)
        self.assertIn("<desc", svg)
        self.assertEqual(len(re.findall(r"<title>", svg)), len(ROWS))

    def test_no_data_renders_nothing(self):
        self.assertEqual(report._tail_chart([]), "")

    def test_the_axis_covers_the_largest_value(self):
        svg = report._tail_chart(ROWS)
        ticks = [int(t.replace(",", "")) for t in
                 re.findall(r'text-anchor="middle"[^>]*>([\d,]+)<', svg)]
        self.assertGreaterEqual(max(ticks), max(r["p95_unhedged"] for r in ROWS))


if __name__ == "__main__":
    unittest.main()
