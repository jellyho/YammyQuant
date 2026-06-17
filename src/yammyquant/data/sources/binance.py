"""Binance data source and a helper to backfill a :class:`DuckDBStore`.

Reads OHLCV klines through ``python-binance`` and returns :class:`Candle`
objects. API keys are read from the environment (``BINANCE_API_KEY`` /
``BINANCE_SECRET_KEY``) and are optional for public market data.
"""

from __future__ import annotations

import os
from datetime import datetime
from typing import Optional

import pandas as pd

from yammyquant.data.candle import Candle, OHLCV_COLUMNS

_KLINE_COLUMNS = [
    "open_time", "open", "high", "low", "close", "volume", "close_time",
    "quote", "trades", "taker_base", "taker_quote", "ignore",
]


def _to_ms(value: Optional[datetime | str]) -> Optional[int]:
    if value is None:
        return None
    if isinstance(value, str):
        value = datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
    return int(value.timestamp() * 1000)


class BinanceSource:
    """Public/authenticated Binance kline reader returning :class:`Candle`."""

    def __init__(self, api_key: Optional[str] = None, secret_key: Optional[str] = None):
        from binance.client import Client  # imported lazily; optional dependency

        self.client = Client(
            api_key or os.getenv("BINANCE_API_KEY"),
            secret_key or os.getenv("BINANCE_SECRET_KEY"),
        )

    def read(
        self,
        ticker: str,
        interval: str,
        start: Optional[datetime | str] = None,
        end: Optional[datetime | str] = None,
    ) -> Candle:
        start_ms, end_ms = _to_ms(start), _to_ms(end)
        if start_ms is None and end_ms is None:
            raw = self.client.get_klines(symbol=ticker, interval=interval)
        else:
            raw = self.client.get_historical_klines(
                symbol=ticker, interval=interval, start_str=start_ms, end_str=end_ms
            )
        df = pd.DataFrame(
            raw,
            columns=_KLINE_COLUMNS,
            index=pd.to_datetime([r[0] for r in raw], unit="ms"),
            dtype=float,
        )
        return Candle(ticker, df[list(OHLCV_COLUMNS)], interval=interval)


def backfill(
    store,
    ticker: str,
    intervals: list[str],
    source: Optional[BinanceSource] = None,
) -> None:
    """Download history from Binance and upsert it into ``store``.

    Resumes from each interval's last stored bar, so re-running only fetches new
    data — the modern equivalent of the old ``SQLUpdater.update()``.
    """
    source = source or BinanceSource()
    for interval in intervals:
        last = store.last_time(ticker, interval)
        start = last if last is not None else datetime.fromtimestamp(0)
        print(f"{datetime.now()} :: {ticker}-{interval} downloading from {start} ...")
        candle = source.read(ticker, interval, start=start, end=datetime.now())
        if len(candle):
            store.write(candle)
        print(f"{datetime.now()} :: {ticker}-{interval} stored {len(candle)} bars.")
