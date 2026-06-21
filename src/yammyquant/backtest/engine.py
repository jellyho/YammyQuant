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
from yammyquant.backtest.order import Action, Order, OrderType
from yammyquant.backtest.portfolio import Portfolio
from yammyquant.strategy.base import Strategy
from yammyquant.metrics.performance import summary

if TYPE_CHECKING:
    from yammyquant.backtest.risk import RiskConfig


def _trigger_price(order: Order, bar_open: float, bar_high: float, bar_low: float):
    """Fill price if a resting LIMIT/STOP order is hit this bar, else ``None``.

    A gap through the level fills at the bar open (you'd never get a worse price
    than the open once it's already through). Limit buys fill at/below the limit,
    limit sells at/above; stops fill once price trades through the trigger.
    """
    p = order.price
    buy = order.action == Action.BUY
    if order.type == OrderType.LIMIT:
        if buy and bar_low <= p:
            return min(bar_open, p)
        if not buy and bar_high >= p:
            return max(bar_open, p)
    elif order.type == OrderType.STOP:
        if buy and bar_high >= p:
            return max(bar_open, p)
        if not buy and bar_low <= p:
            return min(bar_open, p)
    return None


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
        borrow_fee: float = 0.0,
    ):
        if fill_timing not in ("next_open", "close"):
            raise ValueError(f"fill_timing must be 'next_open' or 'close', got {fill_timing!r}")
        from yammyquant.metrics.performance import _BARS_PER_YEAR
        self.candle = candle
        self.strategy = strategy
        self.lookback = lookback or strategy.warmup
        self.fill_timing = fill_timing
        self.allow_short = bool(allow_short)
        self.ppy = _BARS_PER_YEAR.get(candle.interval or "", 252)
        # per-bar borrow cost on short notional (annualized rate / bars-per-year)
        self.borrow_per_bar = float(borrow_fee) / self.ppy if borrow_fee else 0.0
        self.portfolio = Portfolio(cash=cash, fee=fee, allow_short=allow_short)
        self.broker = broker or BacktestBroker(fee=fee, slippage=slippage)
        self.risk = None
        if risk is not None:
            from yammyquant.backtest.risk import RiskManager
            self.risk = RiskManager(risk, self.ppy)

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
        pending: list[Order] = []  # market orders decided last bar, awaiting this bar's open
        working: list[dict] = []   # resting LIMIT/STOP orders: {"order", "placed"}
        self._entry_bar = {}       # ticker -> bar index the open position was entered
        self._hwm = {}             # ticker -> high-water mark since entry (max high / min low)
        self._atr_stop_px = {}     # ticker -> absolute ATR stop level set at entry
        self._atr_take_px = {}     # ticker -> absolute ATR take-profit level set at entry
        self._atr = None
        if self.risk is not None and (self.risk.config.atr_stop or self.risk.config.atr_take):
            self._atr = candle.ind.atr(self.risk.config.atr_lookback).to_numpy()

        for i in range(self.lookback - 1, n):
            window = candle[i - self.lookback + 1 : i + 1]
            ref_price = float(close[i])
            bar_high, bar_low = float(high[i]), float(low[i])
            time = index[i]

            bar_open = float(open_[i])
            touched = False

            # 0) fill market orders decided on the previous bar at THIS bar's open
            if pending:
                for order in pending:
                    fill = self.broker.execute(order, ref_price=bar_open, time=time)
                    if fill is not None:
                        self.portfolio.apply_fill(fill)
                        touched = True
                pending = []

            # 0b) resting LIMIT/STOP orders fill when this bar's range hits them
            if working:
                still = []
                for w in working:
                    if w["placed"] >= i:                 # placed this bar -> eligible next bar
                        still.append(w)
                        continue
                    px = _trigger_price(w["order"], bar_open, bar_high, bar_low)
                    if px is None:
                        still.append(w)                  # still resting
                        continue
                    fill = self.broker.make_fill(w["order"], px, time)
                    if fill is not None:
                        self.portfolio.apply_fill(fill)
                        touched = True
                working = still

            if touched and self.risk is not None:
                self._sync_tracker(ticker, i)

            # 1) protective exits + drawdown kill switch (intrabar, always immediate)
            if self.risk is not None:
                self._apply_risk_exits(ticker, bar_high, bar_low, ref_price, time, i)
                peak_equity = max(peak_equity, self.portfolio.equity())
                if not halted and self.risk.drawdown_breached(peak_equity, self.portfolio.equity()):
                    self._flatten(ticker, ref_price, time)
                    self._sync_tracker(ticker, i)
                    halted = True

            # 2) strategy orders (suppressed once the kill switch has fired)
            if not halted:
                placed_market = False
                for order in self.strategy.on_bar(window):
                    order.time = order.time or time
                    if order.type in (OrderType.LIMIT, OrderType.STOP):
                        self._size_order(order, float(order.price), close, i)
                        working.append({"order": order, "placed": i})   # rest until hit
                    elif next_open:
                        self._size_order(order, ref_price, close, i)
                        pending.append(order)            # market: fill at the next bar's open
                    else:
                        self._size_order(order, ref_price, close, i)
                        fill = self.broker.execute(order, ref_price=ref_price, time=time)
                        if fill is not None:
                            self.portfolio.apply_fill(fill)
                            placed_market = True
                if placed_market and self.risk is not None:
                    self._sync_tracker(ticker, i)

            # update the high-water mark with this bar's range for trailing/breakeven
            if self.risk is not None:
                self._update_hwm(ticker, bar_high, bar_low)

            # carry cost: borrow fee on an open short position, accrued each bar
            if self.borrow_per_bar:
                pos = self.portfolio.position(ticker)
                if pos.is_short:
                    self.portfolio.cash -= abs(pos.quantity) * ref_price * self.borrow_per_bar

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
    def _apply_risk_exits(self, ticker: str, bar_high: float, bar_low: float,
                          ref_price: float, time, i: int) -> None:
        pos = self.portfolio.position(ticker)
        if not pos.is_open:
            return
        is_short = pos.is_short
        avg = pos.avg_price
        hwm = self._hwm.get(ticker, avg)
        # priority: fixed stop/take, then trailing stop, then breakeven, then time stop
        exit_px = self.risk.exit_price(avg, bar_high, bar_low, is_short=is_short)
        if exit_px is None:                              # volatility-scaled ATR stop / take
            sp = self._atr_stop_px.get(ticker)
            tp = self._atr_take_px.get(ticker)
            if sp is not None and (bar_high >= sp if is_short else bar_low <= sp):
                exit_px = sp
            elif tp is not None and (bar_low <= tp if is_short else bar_high >= tp):
                exit_px = tp
        if exit_px is None:
            exit_px = self.risk.trailing_exit(hwm, bar_high, bar_low, is_short=is_short)
        if exit_px is None:
            exit_px = self.risk.breakeven_exit(avg, hwm, bar_high, bar_low, is_short=is_short)
        if exit_px is None and self.risk.config.max_holding_bars is not None:
            entry = self._entry_bar.get(ticker)
            if entry is not None and (i - entry) >= self.risk.config.max_holding_bars:
                exit_px = ref_price   # time stop: exit at this bar's close
        if exit_px is not None:
            self._close(ticker, exit_px, time)
            self._sync_tracker(ticker, i)

    def _sync_tracker(self, ticker: str, i: int) -> None:
        """Record entry bar + reset hwm when a position opens; clear when flat."""
        pos = self.portfolio.position(ticker)
        if pos.is_open:
            if ticker not in self._entry_bar:
                self._entry_bar[ticker] = i
                self._hwm[ticker] = pos.avg_price
                self._set_atr_levels(ticker, pos, i)
        else:
            self._entry_bar.pop(ticker, None)
            self._hwm.pop(ticker, None)
            self._atr_stop_px.pop(ticker, None)
            self._atr_take_px.pop(ticker, None)

    def _set_atr_levels(self, ticker: str, pos, i: int) -> None:
        """Fix volatility-scaled stop/take levels from the ATR at entry."""
        if self._atr is None:
            return
        a = float(self._atr[i]) if i < len(self._atr) else float("nan")
        if a != a or a <= 0:                       # NaN during warmup or no range
            return
        c = self.risk.config
        sign = -1 if pos.is_short else 1
        if c.atr_stop:
            self._atr_stop_px[ticker] = pos.avg_price - sign * c.atr_stop * a
        if c.atr_take:
            self._atr_take_px[ticker] = pos.avg_price + sign * c.atr_take * a

    def _update_hwm(self, ticker: str, bar_high: float, bar_low: float) -> None:
        pos = self.portfolio.position(ticker)
        if not pos.is_open:
            return
        cur = self._hwm.get(ticker, pos.avg_price)
        self._hwm[ticker] = min(cur, bar_low) if pos.is_short else max(cur, bar_high)

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
        realized = None
        if self.risk.config.sizing == "kelly":
            realized = self._closed_pnls()
        qty = self.risk.size_entry(self.portfolio.equity(), ref_price, recent,
                                   realized_pnls=realized)
        if qty > 0:
            order.quantity = qty

    def _closed_pnls(self):
        """Realized PnL of closed trades so far (for Kelly sizing)."""
        rows = self.portfolio._trades
        return [r["realized_pnl"] for r in rows if r.get("closing")]
