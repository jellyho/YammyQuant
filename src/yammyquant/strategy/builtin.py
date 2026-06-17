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
