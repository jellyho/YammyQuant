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
    """
    Strip XML namespace from a tag string.
    
    Parameters:
    	tag (str): XML tag string with possible namespace
    
    Returns:
    	str: Tag string with XML namespace portion removed
    """
    return _TAG.sub("", tag)


def _text(el, *names: str) -> str:
    """
    Extract text from the first child element matching any of the given tag names.
    
    Parameters:
    	el: An XML element
    	*names: Tag names to search for
    
    Returns:
    	str: The first matching child's text content (stripped), or its href attribute value;
    	empty string if no match is found
    """
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
    """
    Identify the first watched symbol whose name or keywords appear in the item.
    
    Parameters:
    	symbols (dict[str, list[str]]): A mapping of symbol names to lists of associated keywords
    
    Returns:
    	str or None: The name of the first matching symbol, or None if no symbol matches
    """
    text = f"{item.title} {item.summary}".lower()
    for symbol, keywords in symbols.items():
        if any(kw.lower() in text for kw in [symbol, *keywords] if kw):
            return symbol
    return None


class RSSFeed:
    def __init__(self, url: str, source: str = ""):
        """
        Initialize an RSS/Atom feed reader.
        
        Parameters:
        	source (str): Optional label for the feed. Defaults to the feed URL if not provided.
        """
        self.url = url
        self.source = source or url

    def fetch(self) -> list[NewsItem]:
        """
        Fetches the RSS or Atom feed from the configured URL and parses it.
        
        Returns:
        	A list of `NewsItem` objects extracted from the feed.
        """
        import requests  # optional dependency

        resp = requests.get(self.url, timeout=15, headers={"User-Agent": "yammyquant/0.3"})
        resp.raise_for_status()
        return parse_rss(resp.text, source=self.source)
