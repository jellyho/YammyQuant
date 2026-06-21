"""Resample candles to a coarser interval (e.g. 1h -> 4h / 1d).

Collect one fine series and derive the rest instead of fetching every timeframe.
OHLCV aggregates the natural way: open=first, high=max, low=min, close=last,
volume=sum, over left-closed/left-labelled bins (bar stamped at its open time).
"""

from __future__ import annotations

import re

from yammyquant.data.candle import Candle

# our interval units -> pandas offset aliases ("M" = month, "m" = minute)
_UNIT = {"m": "min", "h": "h", "d": "D", "w": "W", "M": "MS"}
_SECONDS = {"m": 60, "h": 3600, "d": 86400, "w": 604800, "M": 2592000}


def _parse(interval: str):
    m = re.fullmatch(r"(\d+)([mhdwM])", interval or "")
    if not m:
        raise ValueError(f"unrecognized interval {interval!r}")
    return int(m.group(1)), m.group(2)


def _pandas_freq(interval: str) -> str:
    n, unit = _parse(interval)
    return f"{n}{_UNIT[unit]}"


def interval_seconds(interval: str) -> int:
    n, unit = _parse(interval)
    return n * _SECONDS[unit]


def resample_candle(candle: Candle, target_interval: str) -> Candle:
    """Aggregate ``candle`` up to ``target_interval`` (must be coarser)."""
    if interval_seconds(target_interval) < interval_seconds(candle.interval or "1m"):
        raise ValueError(
            f"target {target_interval} is finer than source {candle.interval}; "
            "resampling can only coarsen")
    agg = (candle.data.resample(_pandas_freq(target_interval), label="left", closed="left")
           .agg({"open": "first", "high": "max", "low": "min",
                 "close": "last", "volume": "sum"})
           .dropna(subset=["open", "high", "low", "close"]))
    return Candle(candle.ticker, agg, interval=target_interval)
