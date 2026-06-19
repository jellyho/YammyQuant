"""Information layer: RSS parsing, sentiment, news storage, brief, DART/KIS."""

import numpy as np
import pandas as pd
import pytest

from yammyquant.data.candle import Candle
from yammyquant.data.sources.store import DuckDBStore
from yammyquant.state.store import LiveState
from yammyquant.feeds.rss import parse_rss, tag_symbols
from yammyquant.feeds.base import NewsItem
from yammyquant.feeds.sentiment import score_text
from yammyquant.feeds.dart import parse_disclosures
from yammyquant.exchanges.korea_investment import KoreaInvestment
from yammyquant.ops import operator as ops

RSS = """<?xml version="1.0"?>
<rss version="2.0"><channel>
  <item><title>Bitcoin surges to new record high</title>
        <link>https://x.com/a</link><pubDate>Mon, 01 Jan 2024</pubDate>
        <description>&lt;p&gt;BTC rallies hard&lt;/p&gt;</description></item>
  <item><title>Samsung Electronics reports earnings miss</title>
        <link>https://x.com/b</link><description>weak quarter</description></item>
</channel></rss>"""

ATOM = """<?xml version="1.0"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry><title>Ethereum upgrade approved</title><link href="https://y.com/e"/>
         <summary>bullish</summary><updated>2024-01-02</updated></entry>
</feed>"""


def test_parse_rss_and_atom():
    rss = parse_rss(RSS, source="test")
    assert len(rss) == 2
    assert rss[0].title == "Bitcoin surges to new record high"
    assert rss[0].url == "https://x.com/a" and "<p>" not in rss[0].summary
    atom = parse_rss(ATOM, source="t")
    assert atom[0].title == "Ethereum upgrade approved" and atom[0].url == "https://y.com/e"


def test_parse_rss_malformed_returns_empty():
    assert parse_rss("not xml") == []


def test_tag_symbols():
    item = NewsItem(title="Bitcoin surges", summary="btc up")
    assert tag_symbols(item, {"BTCUSDT": ["bitcoin", "btc"]}) == "BTCUSDT"
    assert tag_symbols(NewsItem(title="random news"), {"BTCUSDT": ["bitcoin"]}) is None


def test_sentiment_scoring():
    assert score_text("Bitcoin surges to record high, bullish rally") > 0
    assert score_text("Exchange hacked, market crash and lawsuit") < 0
    assert score_text("the meeting is at noon") == 0.0


def test_news_storage_dedup(tmp_path):
    s = LiveState(tmp_path / "s.db")
    assert s.add_news("BTC up", url="http://a", symbol="BTCUSDT", sentiment=0.5) is True
    assert s.add_news("BTC up dup", url="http://a") is False  # same url
    assert len(s.news(symbol="BTCUSDT")) == 1


def test_collect_news_tags_watchlist(tmp_path, monkeypatch):
    s = LiveState(tmp_path / "s.db")
    s.add_watch("BTCUSDT", "binance", "1d")
    # one feed returning our fixture items
    from yammyquant.feeds import rss as rssmod
    monkeypatch.setattr(rssmod.RSSFeed, "fetch", lambda self: parse_rss(RSS, self.source))
    out = ops.collect_news(s, sources={"test": "http://feed"})
    assert out["tagged"] >= 1
    btc_news = s.news(symbol="BTCUSDT")
    assert btc_news and btc_news[0]["sentiment"] is not None


def test_brief_assembles(tmp_path):
    store = DuckDBStore(tmp_path / "store")
    n = 60
    idx = pd.date_range("2023-01-01", periods=n, freq="1D")
    close = 100 + np.arange(n, dtype=float)
    df = pd.DataFrame({"open": close, "high": close + 1, "low": close - 1,
                       "close": close, "volume": [1.0] * n}, index=idx)
    store.write(Candle("BTCUSDT", df, interval="1d"))
    s = LiveState(tmp_path / "s.db")
    s.add_news("BTC rallies", url="http://a", symbol="BTCUSDT", sentiment=0.5)
    b = ops.brief(store, s, "BTCUSDT")
    assert b["price"] == pytest.approx(159.0)
    assert "features" in b and b["news"] and b["news_sentiment"] == 0.5


def test_dart_parse():
    payload = {"list": [{"corp_name": "삼성전자", "report_nm": "분기보고서",
                         "rcept_no": "20240101", "rcept_dt": "20240101", "rm": ""}]}
    items = parse_disclosures(payload, symbol="005930")
    assert items[0].source == "DART" and "삼성전자" in items[0].title
    assert items[0].url.endswith("20240101") and items[0].symbol == "005930"


def test_kis_fundamentals_parse(monkeypatch):
    ex = KoreaInvestment(appkey="a", appsecret="b", account="12345678-01")
    monkeypatch.setattr(ex, "token", lambda: "tok")
    monkeypatch.setattr(ex, "_request", lambda *a, **k: {
        "output": {"stck_prpr": "70000", "per": "12.5", "pbr": "1.3", "eps": "5600",
                   "bps": "53000", "hts_avls": "4180000", "w52_hgpr": "80000", "w52_lwpr": "60000"}})
    f = ex.fundamentals("005930")
    assert f["price"] == 70000.0 and f["per"] == 12.5 and f["pbr"] == 1.3
