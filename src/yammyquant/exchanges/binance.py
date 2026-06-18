"""Binance — native adapter via ``python-binance`` (no ccxt needed).

Binance already had a resumable data backfill (``data/sources/binance.py``); this
exposes it as a first-class :class:`Exchange` (data + balances + orders) so it
sits alongside Upbit/Bithumb/KIS/Toss in the registry and powers live order
routing without requiring ccxt.
"""

from __future__ import annotations

import os
from typing import Optional

import pandas as pd

from yammyquant.data.candle import Candle, OHLCV_COLUMNS
from yammyquant.data.sources.binance import _KLINE_COLUMNS, _to_ms
from yammyquant.exchanges.base import Exchange


class BinanceExchange(Exchange):
    name = "binance"
    asset_class = "crypto"
    supports_trading = True

    def __init__(self, api_key: Optional[str] = None, secret_key: Optional[str] = None,
                 client=None):
        self._api_key = api_key or os.getenv("BINANCE_API_KEY")
        self._secret = secret_key or os.getenv("BINANCE_SECRET_KEY")
        self._client = client  # injectable for tests

    @property
    def client(self):
        # Constructed lazily — python-binance pings the network on init, so we
        # defer that until an actual call (keeps registry/construction offline).
        if self._client is None:
            from binance.client import Client  # optional dependency

            self._client = Client(self._api_key, self._secret)
        return self._client

    # -- market data -------------------------------------------------------
    def read(self, ticker: str, interval: str = "1d", count: int = 200,
             start=None, end=None) -> Candle:
        start_ms, end_ms = _to_ms(start), _to_ms(end)
        if start_ms is None and end_ms is None:
            raw = self.client.get_klines(symbol=ticker, interval=interval, limit=min(count, 1000))
        else:
            raw = self.client.get_historical_klines(symbol=ticker, interval=interval,
                                                    start_str=start_ms, end_str=end_ms)
        return self._parse_candles(ticker, interval, raw, count)

    @staticmethod
    def _parse_candles(ticker: str, interval: str, raw: list, count: int = 200) -> Candle:
        df = pd.DataFrame(raw, columns=_KLINE_COLUMNS,
                          index=pd.to_datetime([r[0] for r in raw], unit="ms"), dtype=float)
        candle = Candle(ticker, df[list(OHLCV_COLUMNS)], interval=interval)
        return candle[-count:] if count and len(candle) > count else candle

    # -- trading -----------------------------------------------------------
    def balances(self) -> dict:
        return self.client.get_account()

    def create_order(self, ticker: str, side: str, quantity: float,
                     price: Optional[float] = None, order_type: str = "limit") -> dict:
        kwargs = {"symbol": ticker, "side": side.upper(),
                  "type": "MARKET" if order_type == "market" else "LIMIT",
                  "quantity": quantity}
        if kwargs["type"] == "LIMIT":
            kwargs.update(price=str(price), timeInForce="GTC")
        return self.client.create_order(**kwargs)

    def order_status(self, order_id: str, ticker: str) -> dict:
        return self.client.get_order(symbol=ticker, orderId=int(order_id))
