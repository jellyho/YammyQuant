"""Portfolio accounting: cash, positions, trade log and equity curve.

A rewrite of the original ``trade.utils.Portfolio`` with:
  * clean position bookkeeping (quantity + average entry price per ticker),
  * fees applied on both buys and sells,
  * an equity curve recorded via :meth:`mark` (mark-to-market each bar),
  * a structured trade log returned as a pandas DataFrame.

Long-only for now (matching the BUY/SELL action set), but positions are stored
per-ticker so multi-asset portfolios work out of the box.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional

import pandas as pd

from yammyquant.backtest.order import Action, Fill


@dataclass
class Position:
    quantity: float = 0.0
    avg_price: float = 0.0

    @property
    def is_open(self) -> bool:
        return self.quantity > 0


class Portfolio:
    """Tracks cash, holdings and history for a backtest or live run.

    Parameters
    ----------
    cash:
        Starting cash (quote currency, e.g. USDT).
    fee:
        Proportional trade fee, e.g. ``0.001`` for 0.1%.
    """

    def __init__(self, cash: float, fee: float = 0.0):
        self.initial_cash = float(cash)
        self.cash = float(cash)
        self.fee = float(fee)
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
        """Update cash/positions from an executed fill.

        Returns ``True`` if the fill changed state, ``False`` if it was rejected
        (e.g. insufficient cash or holdings).
        """
        ticker = fill.ticker
        pos = self.position(ticker)
        self._last_price[ticker] = fill.fill_price

        if fill.action == Action.BUY:
            gross = fill.fill_price * fill.fill_quantity
            cost = gross + fill.fee
            if cost > self.cash + 1e-9:
                return False
            self.cash -= cost
            new_qty = pos.quantity + fill.fill_quantity
            pos.avg_price = (
                (pos.avg_price * pos.quantity + gross) / new_qty if new_qty else 0.0
            )
            pos.quantity = new_qty
            self._log_trade(fill, realized=0.0)
            return True

        if fill.action == Action.SELL:
            if fill.fill_quantity > pos.quantity + 1e-9:
                return False
            proceeds = fill.fill_price * fill.fill_quantity - fill.fee
            realized = (fill.fill_price - pos.avg_price) * fill.fill_quantity - fill.fee
            self.cash += proceeds
            pos.quantity -= fill.fill_quantity
            if pos.quantity <= 1e-12:
                pos.quantity = 0.0
                pos.avg_price = 0.0
            self._log_trade(fill, realized=realized)
            return True

        return False  # HOLD or unknown

    def mark(self, time: datetime, prices: Dict[str, float]) -> None:
        """Record an equity-curve point given current prices per ticker."""
        self._last_price.update(prices)
        self._equity.append({"time": time, "equity": self.equity(), "cash": self.cash})

    # -- logging -----------------------------------------------------------
    def _log_trade(self, fill: Fill, realized: float) -> None:
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
