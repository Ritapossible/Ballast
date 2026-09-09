"""Overnight news, from Google News RSS.

Gate 1b measured that the earnings calendar separates risky nights at 3.2x, but
the replay showed it covers only 2 of the 6 worst position-nights: scheduled
earnings are a minority of the tail. Macro shocks, guidance, legal rulings and
product events drive the rest, and none of them appear on an earnings calendar.

This is the source that reaches them. Free, keyless, per-ticker, and time-stamped
so items can be confined to the window actually being decided.

Yahoo's feeds return 429 from datacenter IPs and are not usable here.
"""
from __future__ import annotations

import datetime as dt
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass

_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
_ENDPOINT = "https://news.google.com/rss/search?q={}&hl=en-US&gl=US&ceid=US:en"
_TAG = re.compile(r"<[^>]+>")


@dataclass(frozen=True)
class NewsItem:
    title: str
    url: str
    source: str
    published: dt.datetime

    def as_context(self) -> str:
        return f"[{self.published:%Y-%m-%d %H:%M}Z] {self.title} ({self.source})"


def _parse_rfc822(value: str) -> dt.datetime | None:
    from email.utils import parsedate_to_datetime
    try:
        parsed = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=dt.timezone.utc)


def fetch(ticker: str, company: str = "", limit: int = 12) -> list[NewsItem]:
    """Recent headlines for one ticker, newest first."""
    query = urllib.parse.quote_plus(f"{company or ticker} stock" if company
                                    else f"{ticker} stock")
    req = urllib.request.Request(_ENDPOINT.format(query), headers={"User-Agent": _UA})
    try:
        with urllib.request.urlopen(req, timeout=25) as resp:
            root = ET.fromstring(resp.read())
    except Exception:
        return []                      # no news is a valid state, not an error

    items: list[NewsItem] = []
    for node in root.iter("item"):
        title = _TAG.sub("", (node.findtext("title") or "")).strip()
        published = _parse_rfc822(node.findtext("pubDate") or "")
        if not title or published is None:
            continue
        items.append(NewsItem(
            title=title,
            url=(node.findtext("link") or "").strip(),
            source=(node.findtext("source") or "").strip() or "unknown",
            published=published,
        ))
    items.sort(key=lambda i: i.published, reverse=True)
    return items[:limit]


def in_window(items: list[NewsItem], start: dt.datetime, end: dt.datetime
              ) -> list[NewsItem]:
    """Only items published inside [start, end).

    Restricting to the decided window is what keeps the reader honest: a headline
    published after the open cannot inform a decision taken before it.
    """
    return [i for i in items if start <= i.published < end]
