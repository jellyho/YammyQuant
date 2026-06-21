"""Portfolio accounting: cash, positions, trade log and equity curve.

A rewrite of the original ``trade.utils.Portfolio`` with:
  * clean position bookkeeping (quantity + average entry price per ticker),
  * fees applied on both buys and sells,
  * an equity curve recorded via :meth:`mark` (mark-to-market each bar),
  * a structured trade log returned as a pandas DataFrame.

Supports both long and short positions (signed quantity) when ``allow_short``
is set; otherwise long-only. Positions are stored per-ticker so multi-asset
portfolios work out of the box.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List

import pandas as pd

from yammyquant.backtest.order import Action, Fill


@dataclass
class Position:
    quantity: float = 0.0          # signed: > 0 long, < 0 short
    avg_price: float = 0.0

    @property
    def is_open(self) -> bool:
        return abs(self.quantity) > 1e-12

    @property
    def is_long(self) -> bool:
        return self.quantity > 1e-12

    @property
    def is_short(self) -> bool:
        return self.quantity < -1e-12


class Portfolio:
    """Tracks cash, holdings and history for a backtest or live run.

    Parameters
    ----------
    cash:
        Starting cash (quote currency, e.g. USDT).
    fee:
        Proportional trade fee, e.g. ``0.001`` for 0.1%.
    """

    def __init__(self, cash: float, fee: float = 0.0, allow_short: bool = False):
        self.initial_cash = float(cash)
        self.cash = float(cash)
        self.fee = float(fee)
        self.allow_short = bool(allow_short)
        self.positions: Dict[str, Position] = {}
        self._trades: List[dict] = []
        self._equity: List[dict] = []
        self._last_price: Dict[str, float] = {}

    # -- queries -----------------------------------------------------------
    def position(self, ticker: str) -> Position:
        return self.positions.setdefault(ticker, Position())

    def equity(self) -> float:
        """Total mark-to-market value using the last seen prices."""
        holdings = sum(
            pos.quantity * self._last_price.get(ticker, pos.avg_price)
            for ticker, pos in self.positions.items()
        )
        return self.cash + holdings

    # -- mutations ---------------------------------------------------------
    def apply_fill(self, fill: Fill) -> bool:
        """Update cash/positions from an executed fill (signed-position aware).

        BUY adds to the signed quantity, SELL subtracts. A trade that reduces
        the position's magnitude *closes* (realizes PnL); one that grows it
        *opens/extends* (sets the weighted average). When ``allow_short`` is
        False, a SELL cannot drive the position below zero (long-only, the old
        behavior). Returns ``True`` if the fill changed state, ``False`` if it
        was rejected (insufficient cash, or short disallowed).
        """
        ticker = fill.ticker
        pos = self.position(ticker)
        price, qty = fill.fill_price, fill.fill_quantity
        self._last_price[ticker] = price
        if qty <= 0 or fill.action not in (Action.BUY, Action.SELL):
            return False

        side = 1 if fill.action == Action.BUY else -1
        delta = side * qty
        q0 = pos.quantity
        q1 = q0 + delta

        # long-only guard: a SELL may not open/extend a short
        if not self.allow_short and q1 < -1e-12:
            return False
        # cash guard on the buy side (cash actually leaves the account)
        if side > 0 and price * qty + fill.fee > self.cash + 1e-9:
            return False

        # realized PnL accrues only on the portion that reduces |position|
        is_close = q0 != 0.0 and (q0 > 0) != (delta > 0)
        realized = 0.0
        if is_close:
            closed = min(qty, abs(q0))
            gain = (price - pos.avg_price) if q0 > 0 else (pos.avg_price - price)
            realized = gain * closed - fill.fee

        # cash flow: buying spends, selling/shorting receives; fee always paid
        self.cash += -side * price * qty - fill.fee

        # update average entry price
        if abs(q1) <= 1e-12:
            pos.quantity, pos.avg_price = 0.0, 0.0
        elif q0 == 0.0:
            pos.quantity, pos.avg_price = q1, price          # fresh position
        elif (q0 > 0) == (q1 > 0):                           # stayed same side
            if abs(q1) > abs(q0):                            # extended -> weighted avg
                pos.avg_price = (pos.avg_price * abs(q0) + price * qty) / abs(q1)
            pos.quantity = q1                                # partial close -> avg unchanged
        else:                                                # flipped through zero
            pos.quantity, pos.avg_price = q1, price

        self._log_trade(fill, realized=realized, closing=is_close)
        return True

    def mark(self, time: datetime, prices: Dict[str, float]) -> None:
        """Record an equity-curve point given current prices per ticker."""
        self._last_price.update(prices)
        self._equity.append({"time": time, "equity": self.equity(), "cash": self.cash})

    # -- logging -----------------------------------------------------------
    def _log_trade(self, fill: Fill, realized: float, closing: bool = False) -> None:
        pos = self.position(fill.ticker)
        self._trades.append(
            {
                "time": fill.time,
                "ticker": fill.ticker,
                "action": fill.action.value,
                "price": fill.fill_price,
                "quantity": fill.fill_quantity,
                "fee": fill.fee,
                "realized_pnl": realized,
                "closing": closing,         # True when this fill reduced |position|
                "position_qty": pos.quantity,
                "avg_price": pos.avg_price,
                "cash": self.cash,
            }
        )

    # -- exports -----------------------------------------------------------
    @property
    def trades(self) -> pd.DataFrame:
        return pd.DataFrame(self._trades)

    @property
    def equity_curve(self) -> pd.DataFrame:
        df = pd.DataFrame(self._equity)
        if not df.empty:
            df = df.set_index("time")
        return df
