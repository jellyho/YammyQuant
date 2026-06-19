"""Shared types for the information layer."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(slots=True)
class NewsItem:
    title: str
    url: str = ""
    source: str = ""
    summary: str = ""
    published: str = ""
    symbol: str = ""
    sentiment: Optional[float] = None

    def as_record(self) -> dict:
        """
        Convert the NewsItem instance to a dictionary.
        
        Returns:
        	dict: A dictionary containing all fields of the NewsItem (title, url, source, summary, published, symbol, sentiment).
        """
        return {
            "title": self.title, "url": self.url, "source": self.source,
            "summary": self.summary, "published": self.published,
            "symbol": self.symbol, "sentiment": self.sentiment,
        }
