"""Multi-exchange OHLCV via `ccxt`.

freqtrade/jesse get their breadth from `ccxt` (100+ venues). This source brings
the same reach to YammyQuant behind the standard ``read()`` interface, so any
ccxt-supported exchange can feed the store/backtester. Optional dependency:
``pip install 'yammyquant[ccxt]'``.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

import pandas as pd

from yammyquant.data.candle import Candle, OHLCV_COLUMNS


def _to_ms(value: Optional[datetime | str]) -> Optional[int]:
    if value is None:
        return None
    if isinstance(value, str):
        value = datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
    return int(value.timestamp() * 1000)


class CCXTSource:
    """Read candles from any ccxt-supported exchange.

    Parameters
    ----------
    exchange:
        ccxt exchange id, e.g. ``"binance"``, ``"bybit"``, ``"kraken"``, ``"okx"``.
    params:
        Extra constructor kwargs forwarded to the ccxt exchange (e.g. api keys).
    """

    def __init__(self, exchange: str = "binance", **params):
        import ccxt  # optional dependency

        if not hasattr(ccxt, exchange):
            raise ValueError(f"unknown ccxt exchange {exchange!r}")
        self.exchange_id = exchange
        self.client = getattr(ccxt, exchange)(params)

    def read(
        self,
        ticker: str,
        interval: str,
        start: Optional[datetime | str] = None,
        end: Optional[datetime | str] = None,
        limit: int = 1000,
    ) -> Candle:
        """Fetch OHLCV. ``ticker`` uses ccxt symbol format, e.g. ``"BTC/USDT"``.

        Paginates from ``start`` (or the most recent ``limit`` bars if unset)
        until ``end`` or the present.
        """
        since = _to_ms(start)
        end_ms = _to_ms(end)
        rows: list[list] = []
        if since is None:
            rows = self.client.fetch_ohlcv(ticker, timeframe=interval, limit=limit)
        else:
            while True:
                batch = self.client.fetch_ohlcv(ticker, timeframe=interval, since=since, limit=limit)
                if not batch:
                    break
                rows.extend(batch)
                since = batch[-1][0] + 1
                if end_ms is not None and batch[-1][0] >= end_ms:
                    break
                if len(batch) < limit:
                    break

        df = pd.DataFrame(rows, columns=["ts", "open", "high", "low", "close", "volume"])
        if end_ms is not None:
            df = df[df["ts"] <= end_ms]
        df.index = pd.to_datetime(df["ts"], unit="ms")
        return Candle(ticker.replace("/", ""), df[list(OHLCV_COLUMNS)], interval=interval)
