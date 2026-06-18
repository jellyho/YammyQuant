"""Adapter that exposes any ccxt exchange through the :class:`Exchange` interface.

Covers the long tail of foreign venues (Binance, Bybit, OKX, Coinbase, Kraken, …)
and Korean ones ccxt supports (Coinone, Korbit). Optional dep: ``[ccxt]``.
"""

from __future__ import annotations

from typing import Optional

from yammyquant.data.candle import Candle
from yammyquant.exchanges.base import Exchange


class CCXTExchange(Exchange):
    asset_class = "crypto"
    supports_trading = True

    def __init__(self, exchange: str, api_key: Optional[str] = None,
                 secret_key: Optional[str] = None, **params):
        import ccxt  # optional dependency

        if not hasattr(ccxt, exchange):
            raise ValueError(f"unknown ccxt exchange {exchange!r}")
        self.name = exchange
        cfg = {"enableRateLimit": True, **params}
        if api_key:
            cfg["apiKey"] = api_key
        if secret_key:
            cfg["secret"] = secret_key
        self.client = getattr(ccxt, exchange)(cfg)

    def read(self, ticker: str, interval: str = "1d", count: int = 200,
             start=None, end=None) -> Candle:
        from yammyquant.data.sources.ccxt_source import CCXTSource

        src = CCXTSource.__new__(CCXTSource)
        src.exchange_id = self.name
        src.client = self.client
        return src.read(ticker, interval, start=start, end=end, limit=count)

    def balances(self) -> dict:
        return self.client.fetch_balance()

    def create_order(self, ticker: str, side: str, quantity: float,
                     price: Optional[float] = None, order_type: str = "limit") -> dict:
        return self.client.create_order(ticker, order_type, side.lower(), quantity, price)
