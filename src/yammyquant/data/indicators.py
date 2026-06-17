"""Vectorized technical indicators.

This module replaces the old ``finta`` dependency with a small set of
dependency-free, vectorized indicators built directly on pandas/numpy.

Every function takes a :class:`~yammyquant.data.candle.Candle` (or anything
exposing ``open/high/low/close/volume`` as pandas Series) and returns a pandas
``Series`` aligned to the candle's index. Returning Series (not bare arrays)
keeps NaN warm-up periods explicit and makes plotting/alignment trivial.

Indicators are registered in :data:`REGISTRY` so the :class:`Candle` accessor
can expose them dynamically while still failing loudly on unknown names.
"""

from __future__ import annotations

from typing import Callable, Dict

import numpy as np
import pandas as pd

REGISTRY: Dict[str, Callable] = {}


def _register(fn: Callable) -> Callable:
    REGISTRY[fn.__name__] = fn
    return fn


def _close(candle) -> pd.Series:
    return pd.Series(candle.close, index=candle.index, name="close")


@_register
def sma(candle, period: int = 20) -> pd.Series:
    """Simple moving average of close."""
    return _close(candle).rolling(period).mean().rename(f"sma{period}")


@_register
def ema(candle, period: int = 20) -> pd.Series:
    """Exponential moving average of close."""
    return _close(candle).ewm(span=period, adjust=False).mean().rename(f"ema{period}")


@_register
def rsi(candle, period: int = 14) -> pd.Series:
    """Wilder's Relative Strength Index."""
    close = _close(candle)
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(0.0, np.nan)
    out = 100.0 - (100.0 / (1.0 + rs))
    return out.fillna(100.0).rename(f"rsi{period}")


@_register
def atr(candle, period: int = 14) -> pd.Series:
    """Average True Range (Wilder smoothing)."""
    high = pd.Series(candle.high, index=candle.index)
    low = pd.Series(candle.low, index=candle.index)
    close = _close(candle)
    prev_close = close.shift(1)
    true_range = pd.concat(
        [high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1
    ).max(axis=1)
    return true_range.ewm(alpha=1 / period, adjust=False, min_periods=period).mean().rename(
        f"atr{period}"
    )


@_register
def bbands(candle, period: int = 20, std: float = 2.0) -> pd.DataFrame:
    """Bollinger Bands -> DataFrame with columns ``lower/middle/upper``."""
    close = _close(candle)
    middle = close.rolling(period).mean()
    deviation = close.rolling(period).std(ddof=0)
    return pd.DataFrame(
        {
            "lower": middle - std * deviation,
            "middle": middle,
            "upper": middle + std * deviation,
        }
    )


@_register
def macd(candle, fast: int = 12, slow: int = 26, signal: int = 9) -> pd.DataFrame:
    """MACD -> DataFrame with columns ``macd/signal/hist``."""
    close = _close(candle)
    macd_line = (
        close.ewm(span=fast, adjust=False).mean() - close.ewm(span=slow, adjust=False).mean()
    )
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    return pd.DataFrame(
        {"macd": macd_line, "signal": signal_line, "hist": macd_line - signal_line}
    )


class Indicators:
    """Accessor that exposes registered indicators as bound methods.

    ``candle.ind.sma(20)`` resolves to ``indicators.sma(candle, 20)``. Unknown
    names raise ``AttributeError`` (unlike the old ``Candle.__getattr__`` which
    raised a misleading ``IndexError``).
    """

    def __init__(self, candle):
        self._candle = candle

    def __getattr__(self, name: str):
        if name in REGISTRY:
            fn = REGISTRY[name]
            return lambda *args, **kwargs: fn(self._candle, *args, **kwargs)
        raise AttributeError(
            f"Unknown indicator {name!r}. Available: {sorted(REGISTRY)}"
        )

    def __dir__(self):
        return sorted(REGISTRY)
