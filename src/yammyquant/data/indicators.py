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


def _high(candle) -> pd.Series:
    return pd.Series(candle.high, index=candle.index, name="high")


def _low(candle) -> pd.Series:
    return pd.Series(candle.low, index=candle.index, name="low")


def _vol(candle) -> pd.Series:
    return pd.Series(candle.volume, index=candle.index, name="volume")


def _typical(candle) -> pd.Series:
    return (_high(candle) + _low(candle) + _close(candle)) / 3.0


def _wma_calc(s: pd.Series, period: int) -> pd.Series:
    w = np.arange(1, period + 1, dtype=float)
    return s.rolling(period).apply(lambda x: np.dot(x, w) / w.sum(), raw=True)


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


# --------------------------------------------------------------------------
# Moving averages & smoothing
# --------------------------------------------------------------------------
@_register
def wma(candle, period: int = 20) -> pd.Series:
    """Linearly weighted moving average."""
    return _wma_calc(_close(candle), period).rename(f"wma{period}")


@_register
def hma(candle, period: int = 16) -> pd.Series:
    """Hull moving average — low-lag smoothing."""
    half, root = max(period // 2, 1), max(int(np.sqrt(period)), 1)
    raw = 2 * _wma_calc(_close(candle), half) - _wma_calc(_close(candle), period)
    return _wma_calc(raw, root).rename(f"hma{period}")


@_register
def dema(candle, period: int = 20) -> pd.Series:
    """Double exponential moving average."""
    e = _close(candle).ewm(span=period, adjust=False).mean()
    return (2 * e - e.ewm(span=period, adjust=False).mean()).rename(f"dema{period}")


@_register
def tema(candle, period: int = 20) -> pd.Series:
    """Triple exponential moving average."""
    e1 = _close(candle).ewm(span=period, adjust=False).mean()
    e2 = e1.ewm(span=period, adjust=False).mean()
    e3 = e2.ewm(span=period, adjust=False).mean()
    return (3 * e1 - 3 * e2 + e3).rename(f"tema{period}")


@_register
def vwma(candle, period: int = 20) -> pd.Series:
    """Volume-weighted moving average."""
    c, v = _close(candle), _vol(candle)
    return ((c * v).rolling(period).sum() / v.rolling(period).sum().replace(0.0, np.nan)).rename(
        f"vwma{period}"
    )


@_register
def vwap(candle) -> pd.Series:
    """Cumulative volume-weighted average price (session-from-start)."""
    tp, v = _typical(candle), _vol(candle)
    return ((tp * v).cumsum() / v.cumsum().replace(0.0, np.nan)).rename("vwap")


# --------------------------------------------------------------------------
# Momentum / oscillators
# --------------------------------------------------------------------------
@_register
def roc(candle, period: int = 10) -> pd.Series:
    """Rate of change (%)."""
    return (_close(candle).pct_change(period) * 100.0).rename(f"roc{period}")


@_register
def momentum(candle, period: int = 10) -> pd.Series:
    """Price momentum (close - close N bars ago)."""
    c = _close(candle)
    return (c - c.shift(period)).rename(f"mom{period}")


@_register
def trix(candle, period: int = 15) -> pd.Series:
    """TRIX — % rate of change of a triple-smoothed EMA."""
    e1 = _close(candle).ewm(span=period, adjust=False).mean()
    e2 = e1.ewm(span=period, adjust=False).mean()
    e3 = e2.ewm(span=period, adjust=False).mean()
    return (e3.pct_change() * 100.0).rename(f"trix{period}")


@_register
def ppo(candle, fast: int = 12, slow: int = 26) -> pd.Series:
    """Percentage price oscillator (MACD expressed as %)."""
    c = _close(candle)
    fast_ema = c.ewm(span=fast, adjust=False).mean()
    slow_ema = c.ewm(span=slow, adjust=False).mean()
    return ((fast_ema - slow_ema) / slow_ema.replace(0.0, np.nan) * 100.0).rename("ppo")


@_register
def stoch(candle, k: int = 14, d: int = 3) -> pd.DataFrame:
    """Stochastic oscillator -> DataFrame with ``k`` (%K) and ``d`` (%D)."""
    high, low, close = _high(candle), _low(candle), _close(candle)
    lowest, highest = low.rolling(k).min(), high.rolling(k).max()
    fast_k = 100.0 * (close - lowest) / (highest - lowest).replace(0.0, np.nan)
    return pd.DataFrame({"k": fast_k, "d": fast_k.rolling(d).mean()})


@_register
def stoch_rsi(candle, period: int = 14, k: int = 3, d: int = 3) -> pd.DataFrame:
    """Stochastic RSI -> DataFrame with ``k`` and ``d`` (0-100)."""
    r = rsi(candle, period)
    lowest, highest = r.rolling(period).min(), r.rolling(period).max()
    stoch_r = 100.0 * (r - lowest) / (highest - lowest).replace(0.0, np.nan)
    k_line = stoch_r.rolling(k).mean()
    return pd.DataFrame({"k": k_line, "d": k_line.rolling(d).mean()})


@_register
def williams_r(candle, period: int = 14) -> pd.Series:
    """Williams %R (-100..0)."""
    high, low, close = _high(candle), _low(candle), _close(candle)
    highest, lowest = high.rolling(period).max(), low.rolling(period).min()
    return (-100.0 * (highest - close) / (highest - lowest).replace(0.0, np.nan)).rename(
        f"willr{period}"
    )


@_register
def cci(candle, period: int = 20) -> pd.Series:
    """Commodity Channel Index."""
    tp = _typical(candle)
    ma = tp.rolling(period).mean()
    mad = (tp - ma).abs().rolling(period).mean()
    return ((tp - ma) / (0.015 * mad).replace(0.0, np.nan)).rename(f"cci{period}")


# --------------------------------------------------------------------------
# Volatility & channels
# --------------------------------------------------------------------------
@_register
def tr(candle) -> pd.Series:
    """True range."""
    high, low, prev = _high(candle), _low(candle), _close(candle).shift(1)
    return pd.concat([high - low, (high - prev).abs(), (low - prev).abs()], axis=1).max(
        axis=1
    ).rename("tr")


@_register
def natr(candle, period: int = 14) -> pd.Series:
    """Normalized ATR (% of price)."""
    return (atr(candle, period) / _close(candle).replace(0.0, np.nan) * 100.0).rename(
        f"natr{period}"
    )


@_register
def stddev(candle, period: int = 20) -> pd.Series:
    """Rolling standard deviation of close."""
    return _close(candle).rolling(period).std(ddof=0).rename(f"std{period}")


@_register
def zscore(candle, period: int = 20) -> pd.Series:
    """Rolling z-score of close (distance from mean in std units)."""
    c = _close(candle)
    mean = c.rolling(period).mean()
    std = c.rolling(period).std(ddof=0).replace(0.0, np.nan)
    return ((c - mean) / std).rename(f"zscore{period}")


@_register
def bbwidth(candle, period: int = 20, std: float = 2.0) -> pd.Series:
    """Bollinger Band width (upper-lower)/middle — squeeze detector."""
    bb = bbands(candle, period, std)
    return ((bb["upper"] - bb["lower"]) / bb["middle"].replace(0.0, np.nan)).rename(
        f"bbwidth{period}"
    )


@_register
def keltner(candle, period: int = 20, mult: float = 2.0) -> pd.DataFrame:
    """Keltner Channels -> DataFrame with ``lower/middle/upper`` (EMA ± mult·ATR)."""
    middle = _close(candle).ewm(span=period, adjust=False).mean()
    rng = atr(candle, period)
    return pd.DataFrame(
        {"lower": middle - mult * rng, "middle": middle, "upper": middle + mult * rng}
    )


@_register
def donchian(candle, period: int = 20) -> pd.DataFrame:
    """Donchian Channels -> DataFrame with ``lower/middle/upper``."""
    upper = _high(candle).rolling(period).max()
    lower = _low(candle).rolling(period).min()
    return pd.DataFrame({"lower": lower, "middle": (upper + lower) / 2.0, "upper": upper})


@_register
def supertrend(candle, period: int = 10, mult: float = 3.0) -> pd.DataFrame:
    """SuperTrend -> DataFrame with ``supertrend`` line and ``direction`` (+1/-1)."""
    hl2 = (_high(candle) + _low(candle)) / 2.0
    rng = atr(candle, period)
    upper = (hl2 + mult * rng).to_numpy()
    lower = (hl2 - mult * rng).to_numpy()
    close = _close(candle).to_numpy()
    n = len(close)
    fu, fl = upper.copy(), lower.copy()
    for i in range(1, n):
        if np.isnan(upper[i]) or np.isnan(fu[i - 1]):
            continue
        fu[i] = upper[i] if (upper[i] < fu[i - 1] or close[i - 1] > fu[i - 1]) else fu[i - 1]
        fl[i] = lower[i] if (lower[i] > fl[i - 1] or close[i - 1] < fl[i - 1]) else fl[i - 1]
    direction = np.ones(n)
    for i in range(1, n):
        if np.isnan(fu[i - 1]) or np.isnan(fl[i - 1]):
            direction[i] = direction[i - 1]
        elif close[i] > fu[i - 1]:
            direction[i] = 1.0
        elif close[i] < fl[i - 1]:
            direction[i] = -1.0
        else:
            direction[i] = direction[i - 1]
    line = np.where(direction == 1.0, fl, fu)
    return pd.DataFrame({"supertrend": line, "direction": direction}, index=candle.index)


@_register
def psar(candle, step: float = 0.02, max_step: float = 0.2) -> pd.Series:
    """Parabolic SAR (Wilder)."""
    high, low = _high(candle).to_numpy(), _low(candle).to_numpy()
    n = len(high)
    out = np.full(n, np.nan)
    if n < 2:
        return pd.Series(out, index=candle.index, name="psar")
    bull = True
    af, ep, out[0] = step, high[0], low[0]
    for i in range(1, n):
        out[i] = out[i - 1] + af * (ep - out[i - 1])
        if bull:
            if low[i] < out[i]:
                bull, out[i], ep, af = False, ep, low[i], step
            else:
                if high[i] > ep:
                    ep, af = high[i], min(af + step, max_step)
                out[i] = min(out[i], low[i - 1], low[max(i - 2, 0)])
        else:
            if high[i] > out[i]:
                bull, out[i], ep, af = True, ep, high[i], step
            else:
                if low[i] < ep:
                    ep, af = low[i], min(af + step, max_step)
                out[i] = max(out[i], high[i - 1], high[max(i - 2, 0)])
    return pd.Series(out, index=candle.index, name="psar")


@_register
def adx(candle, period: int = 14) -> pd.DataFrame:
    """Average Directional Index -> DataFrame with ``plus_di/minus_di/adx``."""
    high, low = _high(candle), _low(candle)
    up, down = high.diff(), -low.diff()
    plus_dm = pd.Series(np.where((up > down) & (up > 0), up, 0.0), index=candle.index)
    minus_dm = pd.Series(np.where((down > up) & (down > 0), down, 0.0), index=candle.index)
    atr_ = tr(candle).ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    plus_di = 100.0 * plus_dm.ewm(alpha=1 / period, adjust=False, min_periods=period).mean() / atr_
    minus_di = 100.0 * minus_dm.ewm(alpha=1 / period, adjust=False, min_periods=period).mean() / atr_
    dx = 100.0 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0.0, np.nan)
    adx_ = dx.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    return pd.DataFrame({"plus_di": plus_di, "minus_di": minus_di, "adx": adx_})


# --------------------------------------------------------------------------
# Volume
# --------------------------------------------------------------------------
@_register
def obv(candle) -> pd.Series:
    """On-Balance Volume."""
    close, vol = _close(candle), _vol(candle)
    sign = np.sign(close.diff().fillna(0.0))
    return (sign * vol).cumsum().rename("obv")


@_register
def cmf(candle, period: int = 20) -> pd.Series:
    """Chaikin Money Flow."""
    high, low, close, vol = _high(candle), _low(candle), _close(candle), _vol(candle)
    mfm = ((close - low) - (high - close)) / (high - low).replace(0.0, np.nan)
    mfv = mfm * vol
    return (mfv.rolling(period).sum() / vol.rolling(period).sum().replace(0.0, np.nan)).rename(
        f"cmf{period}"
    )


@_register
def mfi(candle, period: int = 14) -> pd.Series:
    """Money Flow Index — volume-weighted RSI."""
    tp, vol = _typical(candle), _vol(candle)
    raw_flow = tp * vol
    delta = tp.diff()
    pos = raw_flow.where(delta > 0, 0.0).rolling(period).sum()
    neg = raw_flow.where(delta < 0, 0.0).rolling(period).sum().replace(0.0, np.nan)
    ratio = pos / neg
    return (100.0 - 100.0 / (1.0 + ratio)).rename(f"mfi{period}")


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
