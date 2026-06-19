"""Feature engineering — turn raw candles into model/signal-ready statistics.

This is the deterministic, offline core of the "stats scraper": given a
:class:`Candle`, it computes a tidy table of features (returns, realized
volatility, volume z-score, RSI, trend ratio, ATR%). The :class:`FeatureStore`
persists them as Parquet next to the candle store so both the operator and the
dashboard can read them.

External/online signals (funding rate, news, on-chain) are pluggable on top —
:func:`binance_funding_rate` is one such collector. Keeping the candle-derived
features dependency-free and deterministic makes the pipeline fully testable.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from yammyquant.data.candle import Candle


def compute_features(candle: Candle, vol_window: int = 20) -> pd.DataFrame:
    """Return a DataFrame of features aligned to the candle's index."""
    close = pd.Series(candle.close, index=candle.index, name="close")
    volume = pd.Series(candle.volume, index=candle.index)

    ret = close.pct_change()
    log_ret = np.log(close).diff()
    realized_vol = ret.rolling(vol_window).std()
    vol_mean = volume.rolling(vol_window).mean()
    vol_std = volume.rolling(vol_window).std().replace(0.0, np.nan)
    volume_z = (volume - vol_mean) / vol_std
    sma = close.rolling(vol_window).mean()

    feats = pd.DataFrame(
        {
            "close": close,
            "return_1": ret,
            "log_return": log_ret,
            f"realized_vol_{vol_window}": realized_vol,
            f"volume_z_{vol_window}": volume_z,
            "rsi_14": candle.ind.rsi(14),
            "trend_ratio": close / sma - 1.0,
            "atr_pct": candle.ind.atr(14) / close,
            "macd_hist": candle.ind.macd()["hist"],
            "adx_14": candle.ind.adx(14)["adx"],
            "stoch_k": candle.ind.stoch()["k"],
            "cci_20": candle.ind.cci(20),
            "willr_14": candle.ind.williams_r(14),
        }
    )
    return feats


def latest_features(candle: Candle, vol_window: int = 20) -> dict:
    """The most recent feature row as a plain dict (for logging/signals)."""
    feats = compute_features(candle, vol_window).iloc[-1]
    return {k: (None if pd.isna(v) else round(float(v), 6)) for k, v in feats.items()}


class FeatureStore:
    """Parquet-backed store for computed features, one file per ticker/interval."""

    def __init__(self, path: str | Path = "feature_store"):
        self.path = Path(path)
        self.path.mkdir(parents=True, exist_ok=True)

    def _file(self, ticker: str, interval: str) -> Path:
        return self.path / f"{ticker}_{interval}.parquet"

    def write(self, ticker: str, interval: str, features: pd.DataFrame) -> None:
        features.to_parquet(self._file(ticker, interval))

    def read(self, ticker: str, interval: str) -> pd.DataFrame:
        file = self._file(ticker, interval)
        if not file.exists():
            raise FileNotFoundError(f"no features for {ticker} {interval}")
        return pd.read_parquet(file)


def binance_funding_rate(ticker: str, limit: int = 100) -> pd.DataFrame:
    """Fetch recent USDT-margined futures funding rates from Binance.

    Online collector (needs network + ``python-binance``); returned as a tidy
    DataFrame indexed by funding time.
    """
    from binance.client import Client  # optional dependency

    import os

    client = Client(os.getenv("BINANCE_API_KEY"), os.getenv("BINANCE_SECRET_KEY"))
    rows = client.futures_funding_rate(symbol=ticker, limit=limit)
    df = pd.DataFrame(rows)
    df["fundingRate"] = df["fundingRate"].astype(float)
    df.index = pd.to_datetime(df["fundingTime"], unit="ms")
    return df[["fundingRate"]]
