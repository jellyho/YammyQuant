"""Information/alt-data layer — news, disclosures, and sentiment.

The collectors here only *gather* raw items (RSS headlines, regulatory
disclosures) into the shared state. The *judgement* — relevance and sentiment —
is done by the operator (Claude Code) reading them via ``yq news`` / ``yq brief``,
so no paid sentiment API is needed. A lightweight keyword scorer
(:func:`~yammyquant.feeds.sentiment.score_text`) provides a cheap automatic
fallback for pipelines.
"""

from yammyquant.feeds.base import NewsItem
from yammyquant.feeds.rss import RSSFeed, parse_rss
from yammyquant.feeds.sentiment import score_text
from yammyquant.feeds.sources import DEFAULT_SOURCES

__all__ = ["NewsItem", "RSSFeed", "parse_rss", "score_text", "DEFAULT_SOURCES"]
