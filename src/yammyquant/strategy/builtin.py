"""Built-in example strategies, ported from the original agents."""

from __future__ import annotations

from typing import List

from yammyquant.data.candle import Candle
from yammyquant.backtest.order import Action, Order
from yammyquant.strategy.base import Strategy


class MACross(Strategy):
    """Moving-average crossover.

    Buys ``size`` units when the fast SMA crosses above the slow SMA, and sells
    ``size`` units on the opposite cross.
    """

    def __init__(self, fast: int = 5, slow: int = 20, size: float = 1.0):
        if fast >= slow:
            raise ValueError("fast period must be smaller than slow period")
        self.fast = fast
        self.slow = slow
        self.size = size
        self.warmup = slow + 1

    def on_bar(self, window: Candle) -> List[Order]:
        fast = window.ind.sma(self.fast).to_numpy()
        slow = window.ind.sma(self.slow).to_numpy()
        price = float(window.close[-1])
        time = window.index[-1]

        crossed_up = fast[-1] > slow[-1] and fast[-2] <= slow[-2]
        crossed_down = fast[-1] < slow[-1] and fast[-2] >= slow[-2]

        if crossed_up:
            return [Order(Action.BUY, window.ticker, self.size, price, time)]
        if crossed_down:
            return [Order(Action.SELL, window.ticker, self.size, price, time)]
        return []


class VolatilityBreakout(Strategy):
    """Larry Williams volatility breakout (the old ``VotalityBreakoutAgent``).

    Enters long when price breaks above the previous bar's range times ``k``,
    and exits at the close of the same bar.
    """

    def __init__(self, k: float = 0.5, size: float = 1.0):
        self.k = k
        self.size = size
        self.warmup = 2

    def on_bar(self, window: Candle) -> List[Order]:
        prev_range = window.high[-2] - window.low[-2]
        target = window.close[-2] + prev_range * self.k
        time = window.index[-1]
        if window.high[-1] > target:
            return [
                Order(Action.BUY, window.ticker, self.size, target, time),
                Order(Action.SELL, window.ticker, self.size, float(window.close[-1]), time),
            ]
        return []


class RSIReversion(Strategy):
    """Mean-reversion on RSI: buy oversold crossings, sell overbought crossings."""

    def __init__(self, period: int = 14, oversold: float = 30.0,
                 overbought: float = 70.0, size: float = 1.0):
        self.period = period
        self.oversold = oversold
        self.overbought = overbought
        self.size = size
        self.warmup = period + 2

    def on_bar(self, window: Candle) -> List[Order]:
        rsi = window.ind.rsi(self.period).to_numpy()
        time = window.index[-1]
        price = float(window.close[-1])
        if rsi[-1] < self.oversold <= rsi[-2]:
            return [Order(Action.BUY, window.ticker, self.size, price, time)]
        if rsi[-1] > self.overbought >= rsi[-2]:
            return [Order(Action.SELL, window.ticker, self.size, price, time)]
        return []


class DonchianBreakout(Strategy):
    """Trend-following channel breakout.

    Buys when close breaks above the highest high of the prior ``period`` bars,
    sells when it breaks below the prior ``period`` low.
    """

    def __init__(self, period: int = 20, size: float = 1.0):
        self.period = period
        self.size = size
        self.warmup = period + 1

    def on_bar(self, window: Candle) -> List[Order]:
        prior_high = window.high[-self.period - 1:-1].max()
        prior_low = window.low[-self.period - 1:-1].min()
        close = float(window.close[-1])
        time = window.index[-1]
        if close > prior_high:
            return [Order(Action.BUY, window.ticker, self.size, close, time)]
        if close < prior_low:
            return [Order(Action.SELL, window.ticker, self.size, close, time)]
        return []


# ==========================================================================
# Trend following
# ==========================================================================
class EMACross(Strategy):
    """Fast/slow EMA crossover — the classic scalper's trend trigger."""

    def __init__(self, fast: int = 9, slow: int = 21, size: float = 1.0):
        if fast >= slow:
            raise ValueError("fast period must be smaller than slow period")
        self.fast, self.slow, self.size = fast, slow, size
        self.warmup = slow + 2

    def on_bar(self, window: Candle) -> List[Order]:
        fast = window.ind.ema(self.fast).to_numpy()
        slow = window.ind.ema(self.slow).to_numpy()
        price, time = float(window.close[-1]), window.index[-1]
        if fast[-1] > slow[-1] and fast[-2] <= slow[-2]:
            return [Order(Action.BUY, window.ticker, self.size, price, time)]
        if fast[-1] < slow[-1] and fast[-2] >= slow[-2]:
            return [Order(Action.SELL, window.ticker, self.size, price, time)]
        return []


class TripleEMATrend(Strategy):
    """Triple-EMA ribbon: enter when fast crosses mid while the ribbon is aligned."""

    def __init__(self, fast: int = 9, mid: int = 21, slow: int = 55, size: float = 1.0):
        if not fast < mid < slow:
            raise ValueError("require fast < mid < slow")
        self.fast, self.mid, self.slow, self.size = fast, mid, slow, size
        self.warmup = slow + 2

    def on_bar(self, window: Candle) -> List[Order]:
        f = window.ind.ema(self.fast).to_numpy()
        m = window.ind.ema(self.mid).to_numpy()
        s = window.ind.ema(self.slow).to_numpy()
        price, time = float(window.close[-1]), window.index[-1]
        if f[-1] > m[-1] and f[-2] <= m[-2] and m[-1] > s[-1]:
            return [Order(Action.BUY, window.ticker, self.size, price, time)]
        if f[-1] < m[-1] and f[-2] >= m[-2]:
            return [Order(Action.SELL, window.ticker, self.size, price, time)]
        return []


class MACDMomentum(Strategy):
    """MACD line / signal crossover — momentum entries and exits."""

    def __init__(self, fast: int = 12, slow: int = 26, signal: int = 9, size: float = 1.0):
        self.fast, self.slow, self.signal, self.size = fast, slow, signal, size
        self.warmup = slow + signal + 2

    def on_bar(self, window: Candle) -> List[Order]:
        m = window.ind.macd(self.fast, self.slow, self.signal)
        line, sig = m["macd"].to_numpy(), m["signal"].to_numpy()
        price, time = float(window.close[-1]), window.index[-1]
        if line[-1] > sig[-1] and line[-2] <= sig[-2]:
            return [Order(Action.BUY, window.ticker, self.size, price, time)]
        if line[-1] < sig[-1] and line[-2] >= sig[-2]:
            return [Order(Action.SELL, window.ticker, self.size, price, time)]
        return []


class SuperTrendFollow(Strategy):
    """Follow SuperTrend direction flips (ATR-based trailing trend)."""

    def __init__(self, period: int = 10, mult: float = 3.0, size: float = 1.0):
        self.period, self.mult, self.size = period, mult, size
        # ATR is an EWM, so the SuperTrend bands/direction only stabilize after
        # several multiples of the period — too small a window never flips.
        self.warmup = period * 5 + 2

    def on_bar(self, window: Candle) -> List[Order]:
        d = window.ind.supertrend(self.period, self.mult)["direction"].to_numpy()
        price, time = float(window.close[-1]), window.index[-1]
        if d[-1] == 1.0 and d[-2] == -1.0:
            return [Order(Action.BUY, window.ticker, self.size, price, time)]
        if d[-1] == -1.0 and d[-2] == 1.0:
            return [Order(Action.SELL, window.ticker, self.size, price, time)]
        return []


class ADXTrend(Strategy):
    """Directional trend, filtered by ADX strength.

    A *state* rule rather than an instantaneous crossover: ADX dips toward zero
    exactly at a +DI/-DI crossover (the trend is just turning), so gating the
    crossover bar by ``ADX > threshold`` essentially never fires. Instead we
    track the "strong uptrend" state (``+DI > -DI`` **and** ``ADX > threshold``)
    and trade when it turns on/off — catching trends that build strength after
    the cross, or DI flips that happen while a trend is already strong.
    """

    def __init__(self, period: int = 14, threshold: float = 25.0, size: float = 1.0):
        self.period, self.threshold, self.size = period, threshold, size
        self.warmup = period * 3 + 2

    def on_bar(self, window: Candle) -> List[Order]:
        a = window.ind.adx(self.period)
        plus, minus, strength = (
            a["plus_di"].to_numpy(), a["minus_di"].to_numpy(), a["adx"].to_numpy())
        price, time = float(window.close[-1]), window.index[-1]
        if any(v != v for v in (plus[-2], minus[-2], strength[-2], plus[-1], minus[-1], strength[-1])):
            return []
        bull_now = plus[-1] > minus[-1] and strength[-1] > self.threshold
        bull_prev = plus[-2] > minus[-2] and strength[-2] > self.threshold
        if bull_now and not bull_prev:
            return [Order(Action.BUY, window.ticker, self.size, price, time)]
        if bull_prev and not bull_now:
            return [Order(Action.SELL, window.ticker, self.size, price, time)]
        return []


class ParabolicSARFlip(Strategy):
    """Trade Parabolic SAR flips relative to price."""

    def __init__(self, step: float = 0.02, max_step: float = 0.2, size: float = 1.0):
        self.step, self.max_step, self.size = step, max_step, size
        self.warmup = 20

    def on_bar(self, window: Candle) -> List[Order]:
        sar = window.ind.psar(self.step, self.max_step).to_numpy()
        close = window.close
        price, time = float(close[-1]), window.index[-1]
        if close[-1] > sar[-1] and close[-2] <= sar[-2]:
            return [Order(Action.BUY, window.ticker, self.size, price, time)]
        if close[-1] < sar[-1] and close[-2] >= sar[-2]:
            return [Order(Action.SELL, window.ticker, self.size, price, time)]
        return []


# ==========================================================================
# Breakout / volatility
# ==========================================================================
class BollingerBreakout(Strategy):
    """Buy a close breaking above the upper band; sell below the lower band."""

    def __init__(self, period: int = 20, std: float = 2.0, size: float = 1.0):
        self.period, self.std, self.size = period, std, size
        self.warmup = period + 2

    def on_bar(self, window: Candle) -> List[Order]:
        bb = window.ind.bbands(self.period, self.std)
        upper, lower = bb["upper"].to_numpy(), bb["lower"].to_numpy()
        close = window.close
        price, time = float(close[-1]), window.index[-1]
        if close[-1] > upper[-1] and close[-2] <= upper[-2]:
            return [Order(Action.BUY, window.ticker, self.size, price, time)]
        if close[-1] < lower[-1] and close[-2] >= lower[-2]:
            return [Order(Action.SELL, window.ticker, self.size, price, time)]
        return []


class KeltnerBreakout(Strategy):
    """Break out of the Keltner Channel (EMA ± ATR)."""

    def __init__(self, period: int = 20, mult: float = 1.5, size: float = 1.0):
        self.period, self.mult, self.size = period, mult, size
        self.warmup = period + 2

    def on_bar(self, window: Candle) -> List[Order]:
        kc = window.ind.keltner(self.period, self.mult)
        upper, lower = kc["upper"].to_numpy(), kc["lower"].to_numpy()
        close = window.close
        price, time = float(close[-1]), window.index[-1]
        if close[-1] > upper[-1] and close[-2] <= upper[-2]:
            return [Order(Action.BUY, window.ticker, self.size, price, time)]
        if close[-1] < lower[-1] and close[-2] >= lower[-2]:
            return [Order(Action.SELL, window.ticker, self.size, price, time)]
        return []


# ==========================================================================
# Mean reversion / scalping
# ==========================================================================
class BollingerReversion(Strategy):
    """Fade band touches: buy when close climbs back above the lower band."""

    def __init__(self, period: int = 20, std: float = 2.0, size: float = 1.0):
        self.period, self.std, self.size = period, std, size
        self.warmup = period + 2

    def on_bar(self, window: Candle) -> List[Order]:
        bb = window.ind.bbands(self.period, self.std)
        upper, lower = bb["upper"].to_numpy(), bb["lower"].to_numpy()
        close = window.close
        price, time = float(close[-1]), window.index[-1]
        if close[-1] > lower[-1] and close[-2] <= lower[-2]:
            return [Order(Action.BUY, window.ticker, self.size, price, time)]
        if close[-1] < upper[-1] and close[-2] >= upper[-2]:
            return [Order(Action.SELL, window.ticker, self.size, price, time)]
        return []


class StochasticScalp(Strategy):
    """%K/%D crossover out of oversold/overbought zones."""

    def __init__(self, k: int = 14, d: int = 3, oversold: float = 20.0,
                 overbought: float = 80.0, size: float = 1.0):
        self.k, self.d, self.oversold, self.overbought, self.size = (
            k, d, oversold, overbought, size)
        self.warmup = k + d + 2

    def on_bar(self, window: Candle) -> List[Order]:
        st = window.ind.stoch(self.k, self.d)
        kk, dd = st["k"].to_numpy(), st["d"].to_numpy()
        price, time = float(window.close[-1]), window.index[-1]
        if kk[-1] > dd[-1] and kk[-2] <= dd[-2] and kk[-2] < self.oversold:
            return [Order(Action.BUY, window.ticker, self.size, price, time)]
        if kk[-1] < dd[-1] and kk[-2] >= dd[-2] and kk[-2] > self.overbought:
            return [Order(Action.SELL, window.ticker, self.size, price, time)]
        return []


class StochRSIScalp(Strategy):
    """Stochastic-RSI %K/%D crossover scalp."""

    def __init__(self, period: int = 14, k: int = 3, d: int = 3, oversold: float = 20.0,
                 overbought: float = 80.0, size: float = 1.0):
        self.period, self.k, self.d = period, k, d
        self.oversold, self.overbought, self.size = oversold, overbought, size
        self.warmup = period * 2 + k + d + 2

    def on_bar(self, window: Candle) -> List[Order]:
        sr = window.ind.stoch_rsi(self.period, self.k, self.d)
        kk, dd = sr["k"].to_numpy(), sr["d"].to_numpy()
        price, time = float(window.close[-1]), window.index[-1]
        if kk[-1] > dd[-1] and kk[-2] <= dd[-2] and kk[-2] < self.oversold:
            return [Order(Action.BUY, window.ticker, self.size, price, time)]
        if kk[-1] < dd[-1] and kk[-2] >= dd[-2] and kk[-2] > self.overbought:
            return [Order(Action.SELL, window.ticker, self.size, price, time)]
        return []


class WilliamsRScalp(Strategy):
    """Williams %R reversal out of extremes."""

    def __init__(self, period: int = 14, oversold: float = -80.0,
                 overbought: float = -20.0, size: float = 1.0):
        self.period, self.oversold, self.overbought, self.size = (
            period, oversold, overbought, size)
        self.warmup = period + 2

    def on_bar(self, window: Candle) -> List[Order]:
        wr = window.ind.williams_r(self.period).to_numpy()
        price, time = float(window.close[-1]), window.index[-1]
        if wr[-1] > self.oversold and wr[-2] <= self.oversold:
            return [Order(Action.BUY, window.ticker, self.size, price, time)]
        if wr[-1] < self.overbought and wr[-2] >= self.overbought:
            return [Order(Action.SELL, window.ticker, self.size, price, time)]
        return []


class CCIReversion(Strategy):
    """Commodity Channel Index reversal at ±threshold."""

    def __init__(self, period: int = 20, threshold: float = 100.0, size: float = 1.0):
        self.period, self.threshold, self.size = period, threshold, size
        # CCI chains two rolling(period) windows (mean, then mean-abs-dev), so it
        # needs ~2*period bars before the latest value is non-NaN.
        self.warmup = period * 2 + 2

    def on_bar(self, window: Candle) -> List[Order]:
        c = window.ind.cci(self.period).to_numpy()
        price, time = float(window.close[-1]), window.index[-1]
        if c[-1] > -self.threshold and c[-2] <= -self.threshold:
            return [Order(Action.BUY, window.ticker, self.size, price, time)]
        if c[-1] < self.threshold and c[-2] >= self.threshold:
            return [Order(Action.SELL, window.ticker, self.size, price, time)]
        return []


class MFIReversion(Strategy):
    """Money Flow Index (volume-weighted RSI) reversal out of extremes."""

    def __init__(self, period: int = 14, oversold: float = 20.0,
                 overbought: float = 80.0, size: float = 1.0):
        self.period, self.oversold, self.overbought, self.size = (
            period, oversold, overbought, size)
        self.warmup = period + 2

    def on_bar(self, window: Candle) -> List[Order]:
        m = window.ind.mfi(self.period).to_numpy()
        price, time = float(window.close[-1]), window.index[-1]
        if m[-1] > self.oversold and m[-2] <= self.oversold:
            return [Order(Action.BUY, window.ticker, self.size, price, time)]
        if m[-1] < self.overbought and m[-2] >= self.overbought:
            return [Order(Action.SELL, window.ticker, self.size, price, time)]
        return []


class VWAPReversion(Strategy):
    """Fade deviations from a rolling volume-weighted price back to the mean."""

    def __init__(self, period: int = 20, threshold: float = 0.01, size: float = 1.0):
        self.period, self.threshold, self.size = period, threshold, size
        self.warmup = period + 2

    def on_bar(self, window: Candle) -> List[Order]:
        vw = window.ind.vwma(self.period).to_numpy()
        close = window.close
        price, time = float(close[-1]), window.index[-1]
        dev_now = (close[-1] - vw[-1]) / vw[-1]
        dev_prev = (close[-2] - vw[-2]) / vw[-2]
        if dev_now < -self.threshold and dev_prev >= -self.threshold:
            return [Order(Action.BUY, window.ticker, self.size, price, time)]
        if dev_now > self.threshold and dev_prev <= self.threshold:
            return [Order(Action.SELL, window.ticker, self.size, price, time)]
        return []


class OpeningRangeBreakout(Strategy):
    """Intraday opening-range breakout — a 5m/15m scalping classic.

    Each calendar day the first ``opening_bars`` bars define an opening range.
    After the range is set, break above its high goes long; a drop back below the
    range low exits. With ``flatten_eod`` (default) the position is closed at the
    next day's open — the right behavior for stock sessions. For 24h crypto, where
    the daily boundary is arbitrary, set ``flatten_eod=False`` to carry the
    position across days (it still exits on a range-low break). Degenerate on
    daily bars (each bar is its own "day").
    """

    warmup = 1

    def __init__(self, opening_bars: int = 6, flatten_eod: bool = True, size: float = 1.0):
        if opening_bars < 1:
            raise ValueError("opening_bars must be >= 1")
        self.opening_bars = int(opening_bars)
        self.flatten_eod = bool(flatten_eod)
        self.size = size
        self.reset()

    def reset(self) -> None:
        self._day = None
        self._hi = self._lo = None
        self._count = 0
        self._side = "FLAT"

    def on_bar(self, window: Candle) -> List[Order]:
        ts = window.index[-1]
        day = ts.normalize() if hasattr(ts, "normalize") else ts
        price = float(window.close[-1])
        hi, lo = float(window.high[-1]), float(window.low[-1])

        # new session: reset the opening range; flatten the carry only for
        # session markets (crypto is 24h, so flatten_eod=False holds across days)
        if day != self._day:
            close_long = self.flatten_eod and self._side == "LONG"
            self._day, self._hi, self._lo, self._count = day, hi, lo, 1
            if close_long:
                self._side = "FLAT"
                return [Order(Action.SELL, window.ticker, self.size, price, ts)]
            return []

        # still building the opening range
        if self._count < self.opening_bars:
            self._hi, self._lo = max(self._hi, hi), min(self._lo, lo)
            self._count += 1
            return []

        # range set: breakout long / break-back exit
        if self._side == "FLAT" and price > self._hi:
            self._side = "LONG"
            return [Order(Action.BUY, window.ticker, self.size, price, ts)]
        if self._side == "LONG" and price < self._lo:
            self._side = "FLAT"
            return [Order(Action.SELL, window.ticker, self.size, price, ts)]
        return []


class VWAPBandScalp(Strategy):
    """Session-VWAP band mean-reversion scalp (intraday).

    Buy when price is stretched below the lower VWAP band (``band`` × rolling
    std of the price-VWAP deviation) and exit when it reverts back to the
    session VWAP. Uses the daily-resetting ``session_vwap`` — intraday only.
    """

    def __init__(self, band: float = 1.5, std_period: int = 20, size: float = 1.0):
        self.band, self.std_period, self.size = band, std_period, size
        self.warmup = std_period + 2

    def on_bar(self, window: Candle) -> List[Order]:
        import pandas as pd
        vw = window.ind.session_vwap().to_numpy()
        close = window.close
        std = pd.Series(close - vw).rolling(self.std_period).std().to_numpy()
        price, time = float(close[-1]), window.index[-1]
        lower, lower_prev = vw[-1] - self.band * std[-1], vw[-2] - self.band * std[-2]
        if close[-1] < lower and close[-2] >= lower_prev:        # stretched below band
            return [Order(Action.BUY, window.ticker, self.size, price, time)]
        if close[-1] >= vw[-1] and close[-2] < vw[-2]:           # reverted to VWAP -> exit
            return [Order(Action.SELL, window.ticker, self.size, price, time)]
        return []


class VolumeSpikeBreakout(Strategy):
    """Breakout confirmed by a volume spike — intraday momentum.

    Go long when the latest bar's volume exceeds ``vol_mult`` × its recent
    average *and* price closes above the prior ``lookback``-bar high; exit on a
    close below the prior ``lookback``-bar low.
    """

    def __init__(self, lookback: int = 20, vol_mult: float = 1.5, size: float = 1.0):
        self.lookback, self.vol_mult, self.size = lookback, vol_mult, size
        self.warmup = lookback + 2

    def on_bar(self, window: Candle) -> List[Order]:
        high, low, close, vol = window.high, window.low, window.close, window.volume
        price, time = float(close[-1]), window.index[-1]
        avg_vol = float(vol[-self.lookback - 1:-1].mean())
        spike = avg_vol > 0 and vol[-1] > self.vol_mult * avg_vol
        if spike and close[-1] > float(high[-self.lookback - 1:-1].max()):
            return [Order(Action.BUY, window.ticker, self.size, price, time)]
        if close[-1] < float(low[-self.lookback - 1:-1].min()):
            return [Order(Action.SELL, window.ticker, self.size, price, time)]
        return []


class MicroPullback(Strategy):
    """Buy a shallow pullback to the fast EMA inside an up-trend; exit on trend break."""

    def __init__(self, fast: int = 9, slow: int = 21, size: float = 1.0):
        self.fast, self.slow, self.size = fast, slow, size
        self.warmup = slow + 2

    def on_bar(self, window: Candle) -> List[Order]:
        ef = window.ind.ema(self.fast).to_numpy()
        es = window.ind.ema(self.slow).to_numpy()
        close = window.close
        price, time = float(close[-1]), window.index[-1]
        if ef[-1] > es[-1] and close[-2] <= ef[-2] and close[-1] > ef[-1]:   # pullback resumes
            return [Order(Action.BUY, window.ticker, self.size, price, time)]
        if ef[-1] < es[-1]:                                                  # trend broke -> exit
            return [Order(Action.SELL, window.ticker, self.size, price, time)]
        return []


class RSI2Reversion(Strategy):
    """Connors RSI(2) mean-reversion scalp with a trend filter.

    Buy a deep oversold RSI(2) dip (``< lower``) *while price is above its long
    ``trend`` SMA* (only buy dips in an up-trend); exit when RSI(2) recovers above
    ``upper``. A short, fast oscillator on a slow trend — the classic Connors edge.
    """

    def __init__(self, period: int = 2, trend: int = 50, lower: float = 10.0,
                 upper: float = 60.0, size: float = 1.0):
        self.period, self.trend = period, trend
        self.lower, self.upper, self.size = lower, upper, size
        self.warmup = trend + period + 2

    def on_bar(self, window: Candle) -> List[Order]:
        r = window.ind.rsi(self.period).to_numpy()
        sma = window.ind.sma(self.trend).to_numpy()
        close = window.close
        price, time = float(close[-1]), window.index[-1]
        if r[-1] < self.lower and close[-1] > sma[-1]:        # oversold dip in an up-trend
            return [Order(Action.BUY, window.ticker, self.size, price, time)]
        if r[-1] > self.upper:                                # mean reverted -> take it
            return [Order(Action.SELL, window.ticker, self.size, price, time)]
        return []


class KeltnerSqueezeBreakout(Strategy):
    """TTM-style squeeze breakout (intraday momentum ignition).

    A *squeeze* is when the Bollinger Bands sit inside the Keltner channels (low
    volatility coiling). Go long when the squeeze releases (bands expand back
    outside Keltner) *and* price breaks above the upper Bollinger band; exit on a
    close back below the Bollinger middle (the basis).
    """

    def __init__(self, period: int = 20, bb_std: float = 2.0, kc_mult: float = 1.5,
                 size: float = 1.0):
        self.period, self.bb_std, self.kc_mult, self.size = period, bb_std, kc_mult, size
        self.warmup = period + 3

    def on_bar(self, window: Candle) -> List[Order]:
        bb = window.ind.bbands(self.period, self.bb_std)
        kc = window.ind.keltner(self.period, self.kc_mult)
        bu, bl, bm = bb["upper"].to_numpy(), bb["lower"].to_numpy(), bb["middle"].to_numpy()
        ku, kl = kc["upper"].to_numpy(), kc["lower"].to_numpy()
        close = window.close
        price, time = float(close[-1]), window.index[-1]
        squeezed_prev = bu[-2] <= ku[-2] and bl[-2] >= kl[-2]   # bands inside Keltner last bar
        released = bu[-1] > ku[-1] or bl[-1] < kl[-1]           # expanding now
        if squeezed_prev and released and close[-1] > bu[-1]:   # release + upside break
            return [Order(Action.BUY, window.ticker, self.size, price, time)]
        if close[-1] < bm[-1]:                                  # lost the basis -> exit
            return [Order(Action.SELL, window.ticker, self.size, price, time)]
        return []


class StochMomentum(Strategy):
    """Trend-aligned stochastic momentum (not a reversal).

    Unlike :class:`StochasticScalp` (which fades extremes), this rides momentum:
    go long on a %K/%D bullish cross that happens **above** the midline
    (``trigger``, default 50) — confirming the move is with the trend, not an
    oversold bounce — and exit when %K crosses back below %D.
    """

    def __init__(self, k: int = 14, d: int = 3, trigger: float = 50.0, size: float = 1.0):
        self.k, self.d, self.trigger, self.size = k, d, trigger, size
        self.warmup = k + d + 2

    def on_bar(self, window: Candle) -> List[Order]:
        st = window.ind.stoch(self.k, self.d)
        kk, dd = st["k"].to_numpy(), st["d"].to_numpy()
        price, time = float(window.close[-1]), window.index[-1]
        if kk[-1] > dd[-1] and kk[-2] <= dd[-2] and kk[-1] > self.trigger:   # bullish cross, in-trend
            return [Order(Action.BUY, window.ticker, self.size, price, time)]
        if kk[-1] < dd[-1] and kk[-2] >= dd[-2]:                             # momentum fading -> exit
            return [Order(Action.SELL, window.ticker, self.size, price, time)]
        return []
