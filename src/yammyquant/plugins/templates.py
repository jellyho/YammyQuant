"""Starter templates for operator-authored strategies, indicators, and skills.

Kept ruff-clean so a freshly scaffolded plugin passes lint and runs immediately.
"""

STRATEGY = '''"""Custom strategy: {name}.

Authored by the operator. Edit the rule in ``on_bar`` and backtest with
``yq backtest <SYMBOL> <INTERVAL> {name}`` — it is auto-registered on load.
"""

from yammyquant.backtest.order import Action, Order
from yammyquant.plugins import strategy
from yammyquant.strategy.base import Strategy


@strategy("{name}")
class {cls}(Strategy):
    """TODO: describe your edge."""

    def __init__(self, fast: int = 10, slow: int = 30, size: float = 1.0):
        if fast >= slow:
            raise ValueError("fast must be < slow")
        self.fast = fast
        self.slow = slow
        self.size = size
        self.warmup = slow + 2

    def on_bar(self, window):
        fast = window.ind.sma(self.fast).to_numpy()
        slow = window.ind.sma(self.slow).to_numpy()
        price = float(window.close[-1])
        time = window.index[-1]
        if fast[-1] > slow[-1] and fast[-2] <= slow[-2]:
            return [Order(Action.BUY, window.ticker, self.size, price, time)]
        if fast[-1] < slow[-1] and fast[-2] >= slow[-2]:
            return [Order(Action.SELL, window.ticker, self.size, price, time)]
        return []
'''

INDICATOR = '''"""Custom indicator: {name}.

Authored by the operator. Use it anywhere via ``candle.ind.{name}(...)`` — it is
auto-registered on load. Return a Series (or DataFrame) aligned to candle.index.
"""

import pandas as pd

from yammyquant.plugins import indicator


@indicator
def {name}(candle, period: int = 14):
    """TODO: compute your indicator."""
    close = pd.Series(candle.close, index=candle.index)
    return close.rolling(period).mean().rename("{name}")
'''

SKILL = '''---
name: {name}
description: TODO — when should the operator (Claude Code) use this skill?
---

# {title}

A reusable playbook the operator wrote for itself. Keep it concrete.

## When to use
TODO

## Steps
1. TODO
2. TODO
3. Record the outcome with `yq journal "..." --importance N`.
'''
