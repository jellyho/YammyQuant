"""Meta-strategies — strategies that wrap other strategies.

:class:`RegimeFilter` gates a base strategy's *entries* by a trend regime: only
take longs while price is above its trend moving average (and, with shorting,
only take shorts below it). Exits always pass through, so you never get trapped.
An optional higher-timeframe factor computes the regime on a coarser timeframe
(e.g. a weekly trend filter on daily bars) — the classic "trade with the bigger
trend" overlay, composable over any of the built-in strategies.
"""

from __future__ import annotations

from typing import List

import numpy as np

from yammyquant.data.candle import Candle
from yammyquant.backtest.order import Action, Order
from yammyquant.strategy.base import Strategy


class RegimeFilter(Strategy):
    """Only let ``base`` enter in the prevailing trend regime.

    Parameters
    ----------
    base:
        The wrapped strategy whose signals are filtered.
    trend_period:
        Lookback for the regime moving average (on the — possibly downsampled —
        close).
    htf_factor:
        Higher-timeframe factor: regime is computed on every ``htf_factor``-th
        bar, anchored at the latest bar (1 = same timeframe).
    """

    def __init__(self, base: Strategy, trend_period: int = 200, htf_factor: int = 1):
        if trend_period < 1 or htf_factor < 1:
            raise ValueError("trend_period and htf_factor must be >= 1")
        self.base = base
        self.trend_period = int(trend_period)
        self.htf_factor = int(htf_factor)
        self.warmup = max(base.warmup, self.trend_period * self.htf_factor)

    def reset(self) -> None:
        self.base.reset()

    def _bullish(self, window: Candle) -> bool:
        c = window.close
        ds = c[::-1][::self.htf_factor][::-1]          # every htf_factor-th bar, anchored at last
        if len(ds) < self.trend_period:
            return True                                # not enough history -> don't block
        return float(ds[-1]) > float(np.mean(ds[-self.trend_period:]))

    def on_bar(self, window: Candle) -> List[Order]:
        if len(window) < self.base.warmup:
            return []
        orders = self.base.on_bar(window[-self.base.warmup:])
        if not orders:
            return []
        bullish = self._bullish(window)
        # suppress long entries against the trend; exits (SELL) always pass so a
        # position is never trapped by the regime gate
        return [o for o in orders if not (o.action == Action.BUY and not bullish)]
