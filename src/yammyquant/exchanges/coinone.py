"""Coinone (코인원) — Korean crypto exchange.

Public candle data is fetched natively from the v2 chart endpoint; authenticated
operations (balances, orders) delegate to ccxt, which maintains Coinone's signed
v2.1 request flow. Docs: https://docs.coinone.co.kr
"""

from __future__ import annotations

import os
from typing import Optional

from yammyquant.data.candle import Candle
from yammyquant.exchanges.base import Exchange, candle_from_records, pick

_INTERVALS = {"1m": "1m", "3m": "3m", "5m": "5m", "10m": "10m", "15m": "15m",
              "30m": "30m", "1h": "1h", "2h": "2h", "4h": "4h", "6h": "6h",
              "1d": "1d", "1w": "1w"}
_OPEN, _HIGH, _LOW, _CLOSE = ("open",), ("high",), ("low",), ("close",)
_VOL = ("target_volume", "volume", "quote_volume")
_TIME = ("timestamp", "time")


class CoinoneExchange(Exchange):
    name = "coinone"
    asset_class = "crypto"
    supports_trading = True
    BASE = "https://api.coinone.co.kr"

    def __init__(self, api_key: Optional[str] = None, secret_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("COINONE_API_KEY")
        self.secret_key = secret_key or os.getenv("COINONE_SECRET_KEY")

    @staticmethod
    def _split(ticker: str) -> tuple[str, str]:
        """``"BTC"`` -> (KRW, BTC); ``"BTC_KRW"`` / ``"BTC/KRW"`` -> (KRW, BTC)."""
        t = ticker.replace("/", "_").upper()
        if "_" in t:
            target, quote = t.split("_", 1)
        else:
            target, quote = t, "KRW"
        return quote, target

    def read(self, ticker: str, interval: str = "1d", count: int = 200,
             start=None, end=None) -> Candle:
        if interval not in _INTERVALS:
            raise ValueError(f"unsupported Coinone interval {interval!r}")
        quote, target = self._split(ticker)
        url = f"{self.BASE}/public/v2/chart/{quote}/{target}"
        raw = self._request("GET", url, params={"interval": _INTERVALS[interval],
                                                "size": min(count, 500)})
        return self._parse_candles(f"{target}{quote}", interval, raw, count)

    @staticmethod
    def _parse_candles(ticker: str, interval: str, raw: dict, count: int = 200) -> Candle:
        rows = raw.get("chart", raw if isinstance(raw, list) else [])
        records = [
            {"time": int(pick(r, _TIME)) * 1_000_000,  # ms -> ns
             "open": pick(r, _OPEN), "high": pick(r, _HIGH), "low": pick(r, _LOW),
             "close": pick(r, _CLOSE), "volume": pick(r, _VOL)}
            for r in rows
        ]
        candle = candle_from_records(ticker, interval, records)
        return candle[-count:] if count and len(candle) > count else candle

    # -- authenticated ops delegate to ccxt -------------------------------
    def _ccxt(self):
        from yammyquant.exchanges.ccxt_adapter import CCXTExchange
        return CCXTExchange("coinone", api_key=self.api_key, secret_key=self.secret_key)

    def balances(self) -> dict:
        return self._ccxt().balances()

    def create_order(self, ticker: str, side: str, quantity: float,
                     price: Optional[float] = None, order_type: str = "limit") -> dict:
        return self._ccxt().create_order(ticker, side, quantity, price, order_type)
