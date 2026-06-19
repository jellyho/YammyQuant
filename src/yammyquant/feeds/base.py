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
        return {
            "title": self.title, "url": self.url, "source": self.source,
            "summary": self.summary, "published": self.published,
            "symbol": self.symbol, "sentiment": self.sentiment,
        }
