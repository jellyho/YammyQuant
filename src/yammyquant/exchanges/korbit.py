"""Korbit (코빗) — Korean crypto exchange.

Public candles fetched natively from the v2 endpoint; authenticated operations
delegate to ccxt. Docs: https://docs.korbit.co.kr
"""

from __future__ import annotations

import os
from typing import Optional

from yammyquant.data.candle import Candle
from yammyquant.exchanges.base import Exchange, candle_from_records, pick

# canonical interval -> Korbit minute count
_INTERVALS = {"1m": 1, "5m": 5, "15m": 15, "30m": 30, "1h": 60, "4h": 240,
              "1d": 1440, "1w": 10080}
_TIME = ("timestamp", "time", "candleDateTime")
_OPEN, _HIGH, _LOW, _CLOSE = ("open",), ("high",), ("low",), ("close",)
_VOL = ("volume", "quoteVolume")


class KorbitExchange(Exchange):
    name = "korbit"
    asset_class = "crypto"
    supports_trading = True
    BASE = "https://api.korbit.co.kr"

    def __init__(self, api_key: Optional[str] = None, secret_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("KORBIT_API_KEY")
        self.secret_key = secret_key or os.getenv("KORBIT_SECRET_KEY")

    @staticmethod
    def _symbol(ticker: str) -> str:
        """``"BTC"`` -> ``"btc_krw"``; ``"BTC/KRW"`` / ``"BTC_KRW"`` -> ``"btc_krw"``."""
        t = ticker.replace("/", "_").lower()
        return t if "_" in t else f"{t}_krw"

    def read(self, ticker: str, interval: str = "1d", count: int = 200,
             start=None, end=None) -> Candle:
        if interval not in _INTERVALS:
            raise ValueError(f"unsupported Korbit interval {interval!r}")
        params = {"symbol": self._symbol(ticker), "interval": _INTERVALS[interval],
                  "limit": min(count, 200)}
        raw = self._request("GET", self.BASE + "/v2/candles", params=params)
        return self._parse_candles(ticker.replace("/", "").replace("_", "").upper(),
                                   interval, raw, count)

    @staticmethod
    def _parse_candles(ticker: str, interval: str, raw, count: int = 200) -> Candle:
        rows = raw.get("data", raw) if isinstance(raw, dict) else raw
        records = [
            {"time": int(pick(r, _TIME)) * 1_000_000 if str(pick(r, _TIME)).isdigit()
             else pick(r, _TIME),
             "open": pick(r, _OPEN), "high": pick(r, _HIGH), "low": pick(r, _LOW),
             "close": pick(r, _CLOSE), "volume": pick(r, _VOL)}
            for r in rows
        ]
        candle = candle_from_records(ticker, interval, records)
        return candle[-count:] if count and len(candle) > count else candle

    # -- authenticated ops delegate to ccxt -------------------------------
    def _ccxt(self):
        from yammyquant.exchanges.ccxt_adapter import CCXTExchange
        return CCXTExchange("korbit", api_key=self.api_key, secret_key=self.secret_key)

    def balances(self) -> dict:
        return self._ccxt().balances()

    def create_order(self, ticker: str, side: str, quantity: float,
                     price: Optional[float] = None, order_type: str = "limit") -> dict:
        return self._ccxt().create_order(ticker, side, quantity, price, order_type)
