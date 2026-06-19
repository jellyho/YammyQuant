"""Default news sources and symbol keyword tags.

Override or extend via the central config (``news_sources`` / ``news_keywords``
keys), so you don't edit this file to add a feed.
"""

# label -> RSS URL  (all keyless public feeds)
DEFAULT_SOURCES = {
    "coindesk": "https://www.coindesk.com/arc/outboundfeeds/rss/",
    "cointelegraph": "https://cointelegraph.com/rss",
    "yahoo_finance": "https://finance.yahoo.com/news/rssindex",
    "cnbc_finance": "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=10000664",
}

# symbol -> extra keywords to match in headlines (symbol string itself is always matched)
DEFAULT_KEYWORDS = {
    "BTCUSDT": ["bitcoin", "btc", "비트코인"],
    "ETHUSDT": ["ethereum", "ether", "eth", "이더리움"],
    "KRW-BTC": ["bitcoin", "btc", "비트코인"],
    "005930": ["samsung electronics", "samsung", "삼성전자"],
}
