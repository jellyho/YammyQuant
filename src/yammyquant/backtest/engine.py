"""The backtest engine — the event loop tying data, strategy and broker together.

Replaces the old ``Environment`` + ``Trader`` pair with a single, explicit loop:

    for each bar i (starting after warmup):
        window  = candle[i-lookback+1 : i+1]
        orders  = strategy.on_bar(window)
        fills   = broker.execute(order, ref_price=close[i])
        portfolio.apply_fill(fill)
        portfolio.mark(time[i], {ticker: close[i]})

This mark-to-market-every-bar design produces a clean equity curve that the
metrics module can summarize.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from yammyquant.data.candle import Candle
from yammyquant.backtest.broker import BacktestBroker, Broker
from yammyquant.backtest.portfolio import Portfolio
from yammyquant.strategy.base import Strategy
from yammyquant.metrics.performance import summary


@dataclass
class BacktestResult:
    """Output of a backtest run."""

    equity_curve: pd.DataFrame
    trades: pd.DataFrame
    stats: dict
    portfolio: Portfolio

    def __str__(self) -> str:
        lines = ["BacktestResult"]
        for k, v in self.stats.items():
            lines.append(f"  {k:>16}: {v}")
        return "\n".join(lines)


class Backtest:
    """Run a :class:`Strategy` over a :class:`Candle` history.

    Parameters
    ----------
    candle:
        Full historical data to simulate over.
    strategy:
        The trading logic.
    cash:
        Starting cash.
    fee:
        Proportional trade fee (passed to portfolio and broker).
    slippage:
        Proportional slippage applied by the broker.
    lookback:
        Number of bars handed to the strategy each step. Defaults to the
        strategy's ``warmup`` (so it always sees enough history).
    broker:
        Optional custom broker; defaults to :class:`BacktestBroker`.
    """

    def __init__(
        self,
        candle: Candle,
        strategy: Strategy,
        cash: float = 10_000.0,
        fee: float = 0.001,
        slippage: float = 0.0,
        lookback: int | None = None,
        broker: Broker | None = None,
    ):
        self.candle = candle
        self.strategy = strategy
        self.lookback = lookback or strategy.warmup
        self.portfolio = Portfolio(cash=cash, fee=fee)
        self.broker = broker or BacktestBroker(fee=fee, slippage=slippage)

    def run(self) -> BacktestResult:
        self.strategy.reset()
        candle = self.candle
        n = len(candle)
        if n < self.lookback:
            raise ValueError(
                f"Not enough data: have {n} bars, need at least lookback={self.lookback}."
            )

        close = candle.close
        index = candle.index
        ticker = candle.ticker

        for i in range(self.lookback - 1, n):
            window = candle[i - self.lookback + 1 : i + 1]
            ref_price = float(close[i])
            time = index[i]

            for order in self.strategy.on_bar(window):
                order.time = order.time or time
                fill = self.broker.execute(order, ref_price=ref_price, time=time)
                if fill is not None:
                    self.portfolio.apply_fill(fill)

            self.portfolio.mark(time, {ticker: ref_price})

        return BacktestResult(
            equity_curve=self.portfolio.equity_curve,
            trades=self.portfolio.trades,
            stats=summary(self.portfolio.equity_curve, self.portfolio.trades, interval=candle.interval),
            portfolio=self.portfolio,
        )
