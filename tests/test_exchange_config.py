"""Central exchange config: resolution precedence, factory wiring, file I/O."""

import json

import pytest

from yammyquant.data.candle import Candle
from yammyquant.exchanges import config as xcfg
from yammyquant.exchanges import get_exchange, list_exchanges
from yammyquant.exchanges.upbit import UpbitExchange
from yammyquant.exchanges.coinone import CoinoneExchange
from yammyquant.exchanges.korbit import KorbitExchange
from yammyquant.exchanges.korea_investment import KoreaInvestment


@pytest.fixture
def cfg_file(tmp_path, monkeypatch):
    path = tmp_path / "yammyquant.config.json"
    monkeypatch.setenv("YAMMYQUANT_CONFIG", str(path))
    # clear any creds that might leak from the real environment
    for var in ["UPBIT_ACCESS_KEY", "UPBIT_SECRET_KEY", "KIS_APPKEY", "KIS_APPSECRET",
                "KIS_ACCOUNT"]:
        monkeypatch.delenv(var, raising=False)
    return path


def test_set_value_writes_central_file(cfg_file):
    xcfg.set_value("upbit", "access_key", "AK")
    xcfg.set_value("upbit", "secret_key", "SK")
    saved = json.loads(cfg_file.read_text())
    assert saved["exchanges"]["upbit"] == {"access_key": "AK", "secret_key": "SK"}


def test_build_exchange_reads_config_file(cfg_file):
    xcfg.set_value("upbit", "access_key", "AK")
    xcfg.set_value("upbit", "secret_key", "SK")
    ex = get_exchange("upbit")
    assert isinstance(ex, UpbitExchange)
    assert ex.access_key == "AK" and ex.secret_key == "SK"


def test_precedence_override_beats_file_beats_env(cfg_file, monkeypatch):
    monkeypatch.setenv("UPBIT_ACCESS_KEY", "from_env")
    # env only
    assert get_exchange("upbit").access_key == "from_env"
    # file beats env
    xcfg.set_value("upbit", "access_key", "from_file")
    assert get_exchange("upbit").access_key == "from_file"
    # explicit override beats file
    assert get_exchange("upbit", access_key="from_override").access_key == "from_override"


def test_options_resolve_with_default(cfg_file):
    # KIS 'paper' option defaults to False; settable centrally
    ex = get_exchange("kis", appkey="a", appsecret="b", account="12345678-01")
    assert isinstance(ex, KoreaInvestment) and ex.paper is False
    xcfg.set_value("kis", "paper", True)
    assert get_exchange("kis", appkey="a", appsecret="b", account="12345678-01").paper is True


def test_default_exchange(cfg_file):
    assert xcfg.default_exchange() == "binance"
    cfg = xcfg.load_config()
    cfg["default_exchange"] = "upbit"
    xcfg.save_config(cfg)
    assert xcfg.default_exchange() == "upbit"


def test_alias_resolves(cfg_file):
    assert isinstance(get_exchange("korea_investment", appkey="a", appsecret="b",
                                   account="12345678-01"), KoreaInvestment)


def test_describe_reports_sources(cfg_file, monkeypatch):
    monkeypatch.setenv("BITHUMB_API_KEY", "x")
    xcfg.set_value("upbit", "access_key", "AK")
    desc = xcfg.describe()
    assert desc["exchanges"]["upbit"]["credentials"]["access_key"] == "config:set"
    assert desc["exchanges"]["bithumb"]["credentials"]["api_key"] == "env:BITHUMB_API_KEY"
    assert desc["exchanges"]["kis"]["credentials"]["appkey"] == "missing"


def test_list_includes_new_native(cfg_file):
    info = list_exchanges()
    for name in ["binance", "upbit", "bithumb", "coinone", "korbit"]:
        assert name in info["native_crypto"]
    assert "kis" in info["native_stock"] and "toss" in info["native_stock"]


# -- Coinone / Korbit native candle parsing --------------------------------
def test_coinone_parse_candles():
    raw = {"result": "success", "chart": [
        {"timestamp": 1704067200000, "open": "100", "high": "110", "low": "95",
         "close": "105", "target_volume": "10"},
        {"timestamp": 1704153600000, "open": "105", "high": "112", "low": "104",
         "close": "108", "target_volume": "8"},
    ]}
    c = CoinoneExchange._parse_candles("BTCKRW", "1d", raw)
    assert isinstance(c, Candle) and len(c) == 2 and c.close[-1] == 108.0


def test_coinone_split():
    assert CoinoneExchange._split("BTC") == ("KRW", "BTC")
    assert CoinoneExchange._split("eth_krw") == ("KRW", "ETH")


def test_korbit_parse_and_symbol():
    assert KorbitExchange._symbol("BTC") == "btc_krw"
    raw = {"data": [
        {"timestamp": 1704067200000, "open": "100", "high": "110", "low": "95",
         "close": "105", "volume": "10"},
    ]}
    c = KorbitExchange._parse_candles("BTCKRW", "1d", raw)
    assert len(c) == 1 and c.high[0] == 110.0
