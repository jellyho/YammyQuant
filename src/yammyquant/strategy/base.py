"""Strategy base class.

A Strategy observes a rolling window of candles and returns orders. This is the
modern equivalent of the old ``trade.core.Agent``.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List

from yammyquant.data.candle import Candle
from yammyquant.backtest.order import Order


class Strategy(ABC):
    """Override :meth:`on_bar` to implement a trading rule.

    The engine calls ``on_bar`` once per bar with a :class:`Candle` window whose
    **last** row is the current (most recent) bar. Return a list of
    :class:`Order` (possibly empty) to act on that bar.
    """

    #: minimum number of bars required before the strategy can act
    warmup: int = 1

    @abstractmethod
    def on_bar(self, window: Candle) -> List[Order]:
        ...

    def reset(self) -> None:
        """Clear any internal state between backtest runs (optional)."""
