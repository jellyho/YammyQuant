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
    fill_timing:
        When to fill strategy-generated orders relative to the bar that
        produced them. ``"next_open"`` (default) queues an order decided on the
        close of bar *i* and fills it at the **open of bar i+1** — the realistic,
        bias-free convention, since you cannot observe a bar's close and trade at
        that same close. ``"close"`` fills on the signal bar's close (the old
        behavior; optimistically biased, kept for comparison/back-compat).
        Protective stop/take-profit and the drawdown kill switch are intrabar
        and always fill immediately regardless of this setting.
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
        fill_timing: str = "next_open",
        allow_short: bool = False,
    ):
        if fill_timing not in ("next_open", "close"):
            raise ValueError(f"fill_timing must be 'next_open' or 'close', got {fill_timing!r}")
        self.candle = candle
        self.strategy = strategy
        self.lookback = lookback or strategy.warmup
        self.fill_timing = fill_timing
        self.allow_short = bool(allow_short)
        self.portfolio = Portfolio(cash=cash, fee=fee, allow_short=allow_short)
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

        open_ = candle.open
        close = candle.close
        high = candle.high
        low = candle.low
        index = candle.index
        ticker = candle.ticker
        peak_equity = self.portfolio.equity()
        halted = False
        next_open = self.fill_timing == "next_open"
        pending: list[Order] = []  # orders decided last bar, awaiting this bar's open

        for i in range(self.lookback - 1, n):
            window = candle[i - self.lookback + 1 : i + 1]
            ref_price = float(close[i])
            time = index[i]

            # 0) fill orders decided on the previous bar at THIS bar's open
            if pending:
                fill_price = float(open_[i])
                for order in pending:
                    fill = self.broker.execute(order, ref_price=fill_price, time=time)
                    if fill is not None:
                        self.portfolio.apply_fill(fill)
                pending = []

            # 1) protective exits + drawdown kill switch (intrabar, always immediate)
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
                    if next_open:
                        pending.append(order)   # fill at the next bar's open
                    else:
                        fill = self.broker.execute(order, ref_price=ref_price, time=time)
                        if fill is not None:
                            self.portfolio.apply_fill(fill)

            self.portfolio.mark(time, {ticker: ref_price})

        # orders decided on the final bar have no next open to fill against — drop
        # them rather than peek at a price that never existed.

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
        exit_px = self.risk.exit_price(pos.avg_price, bar_high, bar_low, is_short=pos.is_short)
        if exit_px is not None:
            self._close(ticker, exit_px, time)

    def _flatten(self, ticker: str, price: float, time) -> None:
        self._close(ticker, price, time)

    def _close(self, ticker: str, price: float, time) -> None:
        """Flatten an open position — SELL a long, BUY back a short."""
        pos = self.portfolio.position(ticker)
        if not pos.is_open:
            return
        action = Action.SELL if pos.is_long else Action.BUY
        order = Order(action, ticker, abs(pos.quantity), price, time)
        fill = self.broker.execute(order, ref_price=price, time=time)
        if fill is not None:
            self.portfolio.apply_fill(fill)

    def _size_order(self, order, ref_price: float, close, i: int) -> None:
        """Resize an *entry* per the risk policy (no-op for sizing='off' / exits).

        Sizes a long entry (BUY while flat/long) or, when shorting is enabled, a
        short entry (SELL while flat/short). Exits keep the order's own quantity.
        """
        if self.risk is None:
            return
        pos = self.portfolio.position(order.ticker)
        opening_long = order.action == Action.BUY and pos.quantity >= -1e-12
        opening_short = (order.action == Action.SELL and self.allow_short
                         and pos.quantity <= 1e-12)
        if not (opening_long or opening_short):
            return
        lookback = self.risk.config.vol_lookback
        recent = None
        if i >= lookback:
            seg = close[i - lookback : i + 1]
            recent = seg[1:] / seg[:-1] - 1.0
        qty = self.risk.size_entry(self.portfolio.equity(), ref_price, recent)
        if qty > 0:
            order.quantity = qty
