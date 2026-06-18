"""Bithumb (빗썸) — major Korean crypto exchange (classic public/private API).

Public candlesticks need no auth. Private endpoints (balance, order) sign with
HMAC-SHA512 over ``endpoint + \\0 + urlencoded_params + \\0 + nonce``, the digest
hex-then-base64 encoded. Docs: https://apidocs.bithumb.com
"""

from __future__ import annotations

import base64
import os
import time
from typing import Optional
from urllib.parse import urlencode

from yammyquant.data.candle import Candle
from yammyquant.exchanges.base import Exchange, candle_from_records, hmac_sha512_hex

# canonical interval -> Bithumb chart interval
_INTERVALS = {"1m": "1m", "3m": "3m", "5m": "5m", "10m": "10m", "30m": "30m",
              "1h": "1h", "6h": "6h", "12h": "12h", "1d": "24h"}


class BithumbExchange(Exchange):
    name = "bithumb"
    asset_class = "crypto"
    supports_trading = True
    BASE = "https://api.bithumb.com"

    def __init__(self, api_key: Optional[str] = None, secret_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("BITHUMB_API_KEY")
        self.secret_key = secret_key or os.getenv("BITHUMB_SECRET_KEY")

    @staticmethod
    def _split(ticker: str) -> tuple[str, str]:
        """``"BTC"`` -> (BTC, KRW); ``"BTC_KRW"`` / ``"BTC/KRW"`` -> (BTC, KRW)."""
        t = ticker.replace("/", "_").upper()
        if "_" in t:
            order, payment = t.split("_", 1)
        else:
            order, payment = t, "KRW"
        return order, payment

    # -- market data -------------------------------------------------------
    def read(self, ticker: str, interval: str = "1d", count: int = 200,
             start=None, end=None) -> Candle:
        if interval not in _INTERVALS:
            raise ValueError(f"unsupported Bithumb interval {interval!r}")
        order, payment = self._split(ticker)
        url = f"{self.BASE}/public/candlestick/{order}_{payment}/{_INTERVALS[interval]}"
        raw = self._request("GET", url)
        return self._parse_candles(f"{order}{payment}", interval, raw, count)

    @staticmethod
    def _parse_candles(ticker: str, interval: str, raw: dict, count: int = 200) -> Candle:
        # data rows: [timestamp_ms, open, close, high, low, volume]
        data = raw.get("data", [])
        records = [
            {"time": int(r[0]) * 1_000_000,  # ms -> ns for pandas to_datetime
             "open": float(r[1]), "close": float(r[2]), "high": float(r[3]),
             "low": float(r[4]), "volume": float(r[5])}
            for r in data
        ]
        candle = candle_from_records(ticker, interval, records)
        return candle[-count:] if count and len(candle) > count else candle

    # -- auth --------------------------------------------------------------
    def _sign(self, endpoint: str, params: dict, nonce: str) -> str:
        query = urlencode(params)
        message = endpoint + chr(0) + query + chr(0) + nonce
        digest_hex = hmac_sha512_hex(self.secret_key, message)
        return base64.b64encode(digest_hex.encode()).decode()

    def _private(self, endpoint: str, params: dict) -> dict:
        if not self.api_key or not self.secret_key:
            raise RuntimeError("Bithumb API keys required (BITHUMB_API_KEY / BITHUMB_SECRET_KEY)")
        nonce = str(int(time.time() * 1000))
        body = {"endpoint": endpoint, **params}
        headers = {
            "Api-Key": self.api_key,
            "Api-Sign": self._sign(endpoint, body, nonce),
            "Api-Nonce": nonce,
            "Content-Type": "application/x-www-form-urlencoded",
        }
        return self._request("POST", self.BASE + endpoint, headers=headers, data=body)

    # -- trading -----------------------------------------------------------
    def balances(self, currency: str = "ALL") -> dict:
        return self._private("/info/balance", {"currency": currency})

    def create_order(self, ticker: str, side: str, quantity: float,
                     price: Optional[float] = None, order_type: str = "limit") -> dict:
        order, payment = self._split(ticker)
        if order_type == "market":
            endpoint = "/trade/market_buy" if side.upper() == "BUY" else "/trade/market_sell"
            return self._private(endpoint, {"order_currency": order, "payment_currency": payment,
                                            "units": str(quantity)})
        endpoint = "/trade/place"
        return self._private(endpoint, {
            "order_currency": order, "payment_currency": payment,
            "type": "bid" if side.upper() == "BUY" else "ask",
            "units": str(quantity), "price": str(price),
        })
