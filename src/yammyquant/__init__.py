"""YammyQuant — a small, modern quant framework.

Public API re-exports the most commonly used building blocks so that user
code can simply ``from yammyquant import Candle, Backtest, MACross``.
"""

from yammyquant.data.candle import Candle
from yammyquant.backtest.order import Action, Order, Fill
from yammyquant.backtest.portfolio import Portfolio
from yammyquant.backtest.broker import BacktestBroker
from yammyquant.backtest.engine import Backtest, BacktestResult
from yammyquant.strategy.base import Strategy
from yammyquant.strategy.builtin import MACross, VolatilityBreakout

__version__ = "0.2.0rc1"

__all__ = [
    "Candle",
    "Action",
    "Order",
    "Fill",
    "Portfolio",
    "BacktestBroker",
    "Backtest",
    "BacktestResult",
    "Strategy",
    "MACross",
    "VolatilityBreakout",
]
