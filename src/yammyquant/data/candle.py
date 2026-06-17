"""The :class:`Candle` time-series container.

A thin, typed wrapper around a pandas ``DataFrame`` of OHLCV data. It keeps the
ergonomics of the original project (``candle.close``, slicing, indicator access)
but with explicit validation and clear error messages.
"""

from __future__ import annotations

from typing import Iterable

import numpy as np
import pandas as pd

from yammyquant.data.indicators import Indicators

OHLCV_COLUMNS = ("open", "high", "low", "close", "volume")


class Candle:
    """An immutable view over OHLCV time-series data.

    Parameters
    ----------
    ticker:
        Symbol the data belongs to, e.g. ``"BTCUSDT"``.
    df:
        DataFrame with a ``DatetimeIndex`` and at least the columns
        ``open, high, low, close, volume``. Extra columns are dropped.
    interval:
        Optional bar interval label (``"1d"``, ``"5m"``, ...), kept as metadata.
    """

    def __init__(self, ticker: str, df: pd.DataFrame, interval: str | None = None):
        missing = [c for c in OHLCV_COLUMNS if c not in df.columns]
        if missing:
            raise ValueError(
                f"DataFrame is missing required OHLCV columns: {missing}. "
                f"Got columns: {list(df.columns)}"
            )
        data = df.loc[:, list(OHLCV_COLUMNS)].astype(float)
        if not isinstance(data.index, pd.DatetimeIndex):
            data.index = pd.to_datetime(data.index)
        self.ticker = ticker
        self.interval = interval
        self._data = data
        self.ind = Indicators(self)

    # -- data access -------------------------------------------------------
    @property
    def data(self) -> pd.DataFrame:
        """The underlying OHLCV DataFrame (read-only view convention)."""
        return self._data

    @property
    def index(self) -> pd.DatetimeIndex:
        return self._data.index

    @property
    def open(self) -> np.ndarray:
        return self._data["open"].to_numpy()

    @property
    def high(self) -> np.ndarray:
        return self._data["high"].to_numpy()

    @property
    def low(self) -> np.ndarray:
        return self._data["low"].to_numpy()

    @property
    def close(self) -> np.ndarray:
        return self._data["close"].to_numpy()

    @property
    def volume(self) -> np.ndarray:
        return self._data["volume"].to_numpy()

    # -- dunder ------------------------------------------------------------
    def __len__(self) -> int:
        return len(self._data)

    def __getitem__(self, item) -> "Candle":
        """Positional slicing. Always returns a :class:`Candle`.

        ``candle[-50:]`` -> last 50 bars; ``candle[i]`` -> single-bar Candle.
        """
        if isinstance(item, slice):
            return Candle(self.ticker, self._data.iloc[item], self.interval)
        if isinstance(item, (int, np.integer)):
            return Candle(self.ticker, self._data.iloc[[int(item)]], self.interval)
        raise TypeError(f"Candle indices must be int or slice, not {type(item).__name__}")

    def __repr__(self) -> str:
        span = ""
        if len(self._data):
            span = f", {self.index[0]} .. {self.index[-1]}"
        return f"<Candle {self.ticker} [{self.interval or '?'}] n={len(self)}{span}>"

    def __str__(self) -> str:
        return f"{self.ticker}-Candle\n{self._data}"

    # -- helpers -----------------------------------------------------------
    def tail(self, n: int) -> "Candle":
        return self[-n:]

    def with_columns(self, **series: Iterable) -> pd.DataFrame:
        """Return a DataFrame combining OHLCV with extra named series.

        Useful for plotting/export: ``candle.with_columns(sma=candle.ind.sma(20))``.
        """
        out = self._data.copy()
        for name, values in series.items():
            out[name] = np.asarray(values)
        return out
