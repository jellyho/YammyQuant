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
from typing import TYPE_CHECKING

import pandas as pd

from yammyquant.data.candle import Candle
from yammyquant.backtest.broker import BacktestBroker, Broker
from yammyquant.backtest.order import Action, Order
from yammyquant.backtest.portfolio import Portfolio
from yammyquant.strategy.base import Strategy
from yammyquant.metrics.performance import summary

if TYPE_CHECKING:
    from yammyquant.backtest.risk import RiskConfig


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
        risk: "RiskConfig | None" = None,
    ):
        self.candle = candle
        self.strategy = strategy
        self.lookback = lookback or strategy.warmup
        self.portfolio = Portfolio(cash=cash, fee=fee)
        self.broker = broker or BacktestBroker(fee=fee, slippage=slippage)
        self.risk = None
        if risk is not None:
            from yammyquant.backtest.risk import RiskManager
            from yammyquant.metrics.performance import _BARS_PER_YEAR
            self.risk = RiskManager(risk, _BARS_PER_YEAR.get(candle.interval or "", 252))

    def run(self) -> BacktestResult:
        self.strategy.reset()
        candle = self.candle
        n = len(candle)
        if n < self.lookback:
            raise ValueError(
                f"Not enough data: have {n} bars, need at least lookback={self.lookback}."
            )

        close = candle.close
        high = candle.high
        low = candle.low
        index = candle.index
        ticker = candle.ticker
        peak_equity = self.portfolio.equity()
        halted = False

        for i in range(self.lookback - 1, n):
            window = candle[i - self.lookback + 1 : i + 1]
            ref_price = float(close[i])
            time = index[i]

            # 1) protective exits + drawdown kill switch (before new orders)
            if self.risk is not None:
                self._apply_risk_exits(ticker, float(high[i]), float(low[i]), time)
                peak_equity = max(peak_equity, self.portfolio.equity())
                if not halted and self.risk.drawdown_breached(peak_equity, self.portfolio.equity()):
                    self._flatten(ticker, ref_price, time)
                    halted = True

            # 2) strategy orders (suppressed once the kill switch has fired)
            if not halted:
                for order in self.strategy.on_bar(window):
                    order.time = order.time or time
                    self._size_order(order, ref_price, close, i)
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

    # -- risk helpers ------------------------------------------------------
    def _apply_risk_exits(self, ticker: str, bar_high: float, bar_low: float, time) -> None:
        pos = self.portfolio.position(ticker)
        if not pos.is_open:
            return
        exit_px = self.risk.exit_price(pos.avg_price, bar_high, bar_low)
        if exit_px is not None:
            self._sell(ticker, pos.quantity, exit_px, time)

    def _flatten(self, ticker: str, price: float, time) -> None:
        pos = self.portfolio.position(ticker)
        if pos.is_open:
            self._sell(ticker, pos.quantity, price, time)

    def _sell(self, ticker: str, quantity: float, price: float, time) -> None:
        order = Order(Action.SELL, ticker, quantity, price, time)
        fill = self.broker.execute(order, ref_price=price, time=time)
        if fill is not None:
            self.portfolio.apply_fill(fill)

    def _size_order(self, order, ref_price: float, close, i: int) -> None:
        """Resize a BUY entry per the risk policy (no-op for sizing='off'/SELL)."""
        if self.risk is None or order.action != Action.BUY:
            return
        lookback = self.risk.config.vol_lookback
        recent = None
        if i >= lookback:
            seg = close[i - lookback : i + 1]
            recent = seg[1:] / seg[:-1] - 1.0
        qty = self.risk.size_entry(self.portfolio.equity(), ref_price, recent)
        if qty > 0:
            order.quantity = qty
