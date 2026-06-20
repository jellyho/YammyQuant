"""Exchange adapters: candle parsing, auth signing, payload building (mocked HTTP).

Live network calls are not exercised — these tests pin the deterministic logic
(parsing, JWT/HMAC signing, request building, registry wiring).
"""

import base64
import hashlib
import hmac
import json

import pytest

from yammyquant.data.candle import Candle
from yammyquant.exchanges import get_exchange, list_exchanges
from yammyquant.exchanges.base import jwt_hs256
from yammyquant.exchanges.binance import BinanceExchange
from yammyquant.exchanges.upbit import UpbitExchange
from yammyquant.exchanges.bithumb import BithumbExchange
from yammyquant.exchanges.korea_investment import KoreaInvestment
from yammyquant.exchanges.toss import TossSecurities


class _FakeBinanceClient:
    def __init__(self):
        self.orders = []

    def get_klines(self, symbol, interval, limit):
        # [open_time, open, high, low, close, volume, close_time, q, n, tb, tq, ignore]
        return [
            [1704067200000, "100", "110", "95", "105", "10", 0, 0, 0, 0, 0, 0],
            [1704153600000, "105", "112", "104", "108", "8", 0, 0, 0, 0, 0, 0],
        ]

    def create_order(self, **kwargs):
        self.orders.append(kwargs)
        return {"orderId": 1, **kwargs}


# -- shared JWT -------------------------------------------------------------
def test_jwt_hs256_verifiable():
    token = jwt_hs256({"access_key": "abc", "nonce": "n1"}, "secret")
    header_b64, body_b64, sig_b64 = token.split(".")
    signing_input = f"{header_b64}.{body_b64}".encode()
    expected = base64.urlsafe_b64encode(
        hmac.new(b"secret", signing_input, hashlib.sha256).digest()
    ).rstrip(b"=").decode()
    assert sig_b64 == expected
    payload = json.loads(base64.urlsafe_b64decode(body_b64 + "=="))
    assert payload["access_key"] == "abc"


# -- registry ---------------------------------------------------------------
def test_registry_resolves_native():
    assert isinstance(get_exchange("upbit"), UpbitExchange)
    assert isinstance(get_exchange("bithumb"), BithumbExchange)
    assert isinstance(get_exchange("kis"), KoreaInvestment)
    assert isinstance(get_exchange("toss"), TossSecurities)


def test_list_exchanges_shape():
    info = list_exchanges()
    assert "upbit" in info["native_crypto"] and "binance" in info["native_crypto"]
    assert any("toss" in s for s in info["native_stock"])


# -- Binance ----------------------------------------------------------------
def test_binance_read_parses_klines():
    ex = BinanceExchange(client=_FakeBinanceClient())
    c = ex.read("BTCUSDT", "1d", count=200)
    assert isinstance(c, Candle) and len(c) == 2
    assert c.open[0] == 100.0 and c.close[-1] == 108.0


def test_binance_create_order_maps_type_and_side():
    fake = _FakeBinanceClient()
    ex = BinanceExchange(client=fake)
    ex.create_order("BTCUSDT", "buy", 0.5, price=50000, order_type="limit")
    assert fake.orders[0] == {"symbol": "BTCUSDT", "side": "BUY", "type": "LIMIT",
                              "quantity": 0.5, "price": "50000", "timeInForce": "GTC"}
    ex.create_order("BTCUSDT", "SELL", 0.5, order_type="market")
    assert fake.orders[1]["type"] == "MARKET" and "price" not in fake.orders[1]


# -- Upbit ------------------------------------------------------------------
UPBIT_RAW = [
    {"candle_date_time_kst": "2024-01-02T00:00:00", "opening_price": 100, "high_price": 110,
     "low_price": 95, "trade_price": 105, "candle_acc_trade_volume": 12.5},
    {"candle_date_time_kst": "2024-01-01T00:00:00", "opening_price": 90, "high_price": 101,
     "low_price": 88, "trade_price": 100, "candle_acc_trade_volume": 10.0},
]


def test_upbit_parse_candles_sorted_ascending():
    c = UpbitExchange._parse_candles("KRW-BTC", "1d", UPBIT_RAW)
    assert isinstance(c, Candle) and len(c) == 2
    assert c.open[0] == 90.0 and c.close[-1] == 105.0  # oldest first
    assert c.ticker == "KRWBTC"


def test_upbit_interval_mapping():
    assert UpbitExchange._candle_request("KRW-BTC", "1h", 200, None)[0] == "/v1/candles/minutes/60"
    assert UpbitExchange._candle_request("KRW-BTC", "1d", 200, None)[0] == "/v1/candles/days"
    with pytest.raises(ValueError):
        UpbitExchange._candle_request("KRW-BTC", "2h", 200, None)


def test_upbit_auth_headers_include_query_hash():
    ex = UpbitExchange(access_key="ak", secret_key="sk")
    headers = ex._auth_headers({"market": "KRW-BTC", "side": "bid"})
    token = headers["Authorization"].removeprefix("Bearer ")
    payload = json.loads(base64.urlsafe_b64decode(token.split(".")[1] + "=="))
    assert payload["query_hash_alg"] == "SHA512" and "query_hash" in payload


def test_upbit_order_maps_side_and_calls_request(monkeypatch):
    ex = UpbitExchange(access_key="ak", secret_key="sk")
    captured = {}
    monkeypatch.setattr(ex, "_request", lambda *a, **k: captured.update(k) or {"uuid": "x"})
    ex.create_order("KRW-BTC", "BUY", 0.1, price=50000, order_type="limit")
    assert captured["json_body"]["side"] == "bid"
    assert captured["json_body"]["ord_type"] == "limit"


def test_upbit_read_via_mock(monkeypatch):
    ex = UpbitExchange()
    monkeypatch.setattr(ex, "_request", lambda *a, **k: UPBIT_RAW)
    assert len(ex.read("KRW-BTC", "1d")) == 2


# -- Bithumb (API 2.0, Upbit-compatible) ------------------------------------
def test_bithumb_market_normalisation():
    assert BithumbExchange._market("BTC") == "KRW-BTC"
    assert BithumbExchange._market("KRW-BTC") == "KRW-BTC"
    assert BithumbExchange._market("btc_krw") == "KRW-BTC"
    assert BithumbExchange._market("ETH/KRW") == "KRW-ETH"


def test_bithumb_interval_mapping():
    assert BithumbExchange._candle_request("KRW-BTC", "1h", 200, None)[0] == "/v1/candles/minutes/60"
    assert BithumbExchange._candle_request("KRW-BTC", "1d", 200, None)[0] == "/v1/candles/days"
    with pytest.raises(ValueError):
        BithumbExchange._candle_request("KRW-BTC", "2h", 200, None)


def test_bithumb_parse_candles():
    raw = [
        {"candle_date_time_kst": "2024-01-02T00:00:00", "opening_price": 105, "high_price": 112,
         "low_price": 104, "trade_price": 108, "candle_acc_trade_volume": 8.0},
        {"candle_date_time_kst": "2024-01-01T00:00:00", "opening_price": 100, "high_price": 110,
         "low_price": 95, "trade_price": 105, "candle_acc_trade_volume": 10.0},
    ]
    c = BithumbExchange._parse_candles("KRW-BTC", "1d", raw)
    assert len(c) == 2 and c.close[0] == 105.0 and c.high[1] == 112.0  # oldest first
    assert c.ticker == "KRWBTC"


def test_bithumb_auth_headers_include_query_hash():
    ex = BithumbExchange(api_key="k", secret_key="s")
    headers = ex._auth_headers({"market": "KRW-BTC", "side": "bid"})
    token = headers["Authorization"].removeprefix("Bearer ")
    payload = json.loads(base64.urlsafe_b64decode(token.split(".")[1] + "=="))
    assert payload["query_hash_alg"] == "SHA512" and "query_hash" in payload
    assert payload["access_key"] == "k"


def test_bithumb_order_maps_side_and_calls_request(monkeypatch):
    ex = BithumbExchange(api_key="k", secret_key="s")
    captured = {}
    monkeypatch.setattr(ex, "_request", lambda *a, **k: captured.update(k) or {"uuid": "x"})
    ex.create_order("BTC", "SELL", 0.1, price=50000, order_type="limit")
    assert captured["json_body"]["side"] == "ask"
    assert captured["json_body"]["market"] == "KRW-BTC"


# -- KIS (Korean stocks) ----------------------------------------------------
def test_kis_parse_candles():
    raw = {"output2": [
        {"stck_bsop_date": "20240102", "stck_oprc": "100", "stck_hgpr": "110",
         "stck_lwpr": "95", "stck_clpr": "105", "acml_vol": "1000"},
        {"stck_bsop_date": "20240101", "stck_oprc": "90", "stck_hgpr": "101",
         "stck_lwpr": "88", "stck_clpr": "100", "acml_vol": "900"},
    ]}
    c = KoreaInvestment._parse_candles("005930", "1d", raw)
    assert len(c) == 2 and c.open[0] == 90.0 and c.close[-1] == 105.0


def test_kis_account_parts():
    ex = KoreaInvestment(account="12345678-01")
    assert ex._account_parts() == ("12345678", "01")


def test_kis_order_trid_real_vs_paper(monkeypatch):
    for paper, expected in [(False, "TTTC0802U"), (True, "VTTC0802U")]:
        ex = KoreaInvestment(appkey="a", appsecret="b", account="12345678-01", paper=paper)
        seen = {}
        monkeypatch.setattr(ex, "token", lambda: "tok")
        monkeypatch.setattr(ex, "_hashkey", lambda body: "HASH")
        monkeypatch.setattr(ex, "_request",
                            lambda method, url, headers=None, **k: seen.update(headers) or {"rt_cd": "0"})
        ex.create_order("005930", "BUY", 10, price=70000)
        assert seen["tr_id"] == expected


def test_kis_rejects_intraday_interval():
    with pytest.raises(ValueError):
        KoreaInvestment(appkey="a", appsecret="b", account="12345678-01").read("005930", "1h")


# -- Toss -------------------------------------------------------------------
def test_toss_parse_candles_with_aliases():
    raw = {"candles": [
        {"date": "2024-01-01", "open": 100, "high": 110, "low": 95, "close": 105, "volume": 10},
        {"date": "2024-01-02", "openPrice": 105, "highPrice": 112, "lowPrice": 104,
         "closePrice": 108, "tradingVolume": 8},
    ]}
    c = TossSecurities._parse_candles("005930", "1d", raw)
    assert len(c) == 2 and c.close[0] == 105.0 and c.close[-1] == 108.0


def test_toss_order_body(monkeypatch):
    ex = TossSecurities(app_key="k", app_secret="s", account="acc")
    seen = {}
    monkeypatch.setattr(ex, "token", lambda: "tok")
    monkeypatch.setattr(ex, "_request",
                        lambda method, url, headers=None, json_body=None, **k: seen.update(json_body or {}) or {})
    ex.create_order("005930", "SELL", 5, price=70000)
    assert seen["side"] == "SELL" and seen["symbol"] == "005930" and seen["quantity"] == 5
