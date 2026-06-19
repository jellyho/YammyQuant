"""RSS/Atom news reader — stdlib XML parsing, no extra dependency, no API key.

Most crypto and finance outlets publish RSS, so this covers a lot of ground for
free. ``parse_rss`` is pure (testable on fixture XML); ``RSSFeed.fetch`` adds the
network call.
"""

from __future__ import annotations

import re
from typing import Optional
from xml.etree import ElementTree as ET

from yammyquant.feeds.base import NewsItem

_TAG = re.compile(r"\{.*\}")          # strip XML namespaces
_HTML = re.compile(r"<[^>]+>")        # strip HTML from summaries


def _local(tag: str) -> str:
    return _TAG.sub("", tag)


def _text(el, *names: str) -> str:
    for child in el:
        if _local(child.tag) in names and (child.text or child.attrib.get("href")):
            return (child.text or child.attrib.get("href", "")).strip()
    return ""


def parse_rss(xml: str, source: str = "") -> list[NewsItem]:
    """Parse RSS 2.0 or Atom XML into NewsItems (namespace/format tolerant)."""
    try:
        root = ET.fromstring(xml.strip())
    except ET.ParseError:
        return []
    items = []
    for el in root.iter():
        if _local(el.tag) not in ("item", "entry"):
            continue
        title = _text(el, "title")
        if not title:
            continue
        summary = _HTML.sub("", _text(el, "description", "summary", "content")).strip()
        items.append(NewsItem(
            title=title.strip(),
            url=_text(el, "link", "id"),
            source=source,
            summary=summary[:500],
            published=_text(el, "pubDate", "published", "updated"),
        ))
    return items


def tag_symbols(item: NewsItem, symbols: dict[str, list[str]]) -> Optional[str]:
    """Return the first watched symbol whose name/keywords appear in the headline."""
    text = f"{item.title} {item.summary}".lower()
    for symbol, keywords in symbols.items():
        if any(kw.lower() in text for kw in [symbol, *keywords] if kw):
            return symbol
    return None


class RSSFeed:
    def __init__(self, url: str, source: str = ""):
        self.url = url
        self.source = source or url

    def fetch(self) -> list[NewsItem]:
        import requests  # optional dependency

        resp = requests.get(self.url, timeout=15, headers={"User-Agent": "yammyquant/0.3"})
        resp.raise_for_status()
        return parse_rss(resp.text, source=self.source)
