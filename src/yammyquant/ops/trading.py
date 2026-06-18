"""Trade management over the shared :class:`LiveState`.

Two modes:
  * **paper** — fills immediately against a simulated cash/position book.
  * **live** — creates a ``pending`` trade that a human must approve (in the
    dashboard or CLI). Approval only places a real order when the environment
    explicitly opts in via ``YQ_ALLOW_LIVE=1`` *and* Binance keys are present.

This is the only component allowed to move money, so the guardrails live here:
live orders never execute without (1) the env flag and (2) explicit approval.
"""

from __future__ import annotations

import os
from typing import Callable, Optional

from yammyquant.state.store import LiveState


def live_trading_allowed() -> bool:
    """Live orders are placed only when this is explicitly enabled."""
    return os.getenv("YQ_ALLOW_LIVE") == "1"


class TradeManager:
    def __init__(self, state: LiveState, fee: float = 0.001):
        self.state = state
        self.fee = fee

    # -- cash --------------------------------------------------------------
    @property
    def cash(self) -> float:
        return float(self.state.get("cash", 10_000.0))

    @cash.setter
    def cash(self, value: float) -> None:
        self.state.set("cash", float(value))

    # -- submission --------------------------------------------------------
    def submit(
        self,
        ticker: str,
        side: str,
        quantity: float,
        price: float,
        mode: str = "paper",
        rationale: str = "",
    ) -> dict:
        """Submit an order. Paper fills now; live is queued for approval."""
        side = side.upper()
        if side not in ("BUY", "SELL"):
            raise ValueError("side must be BUY or SELL")
        if quantity <= 0:
            raise ValueError("quantity must be positive")

        if mode == "live":
            trade_id = self.state.add_trade(
                ticker, side, quantity, price, "live", "pending", rationale
            )
            self.state.log(
                "trade",
                f"LIVE {side} {quantity} {ticker} @ {price} queued for approval (#{trade_id})",
                trade_id=trade_id,
            )
            return self.state.get_trade(trade_id)

        # paper: fill immediately
        trade_id = self.state.add_trade(
            ticker, side, quantity, price, "paper", "pending", rationale
        )
        self._fill(trade_id, ticker, side, quantity, price)
        return self.state.get_trade(trade_id)

    # -- approval (live) ---------------------------------------------------
    def approve(self, trade_id: int, place_live: Optional[Callable] = None) -> dict:
        """Approve a pending trade. For live trades this places the real order."""
        trade = self.state.get_trade(trade_id)
        if trade is None:
            raise ValueError(f"no such trade #{trade_id}")
        if trade["status"] != "pending":
            raise ValueError(f"trade #{trade_id} is {trade['status']}, not pending")

        if trade["mode"] == "live":
            if not live_trading_allowed():
                self.state.set_trade_status(trade_id, "rejected")
                self.state.log(
                    "trade",
                    f"LIVE trade #{trade_id} rejected: YQ_ALLOW_LIVE not set",
                    trade_id=trade_id,
                )
                return self.state.get_trade(trade_id)
            placer = place_live or self._place_live_order
            placer(trade)

        self._fill(trade_id, trade["ticker"], trade["side"],
                   trade["quantity"], trade["price"])
        self.state.log("trade", f"approved & filled trade #{trade_id}", trade_id=trade_id)
        return self.state.get_trade(trade_id)

    def reject(self, trade_id: int) -> dict:
        self.state.set_trade_status(trade_id, "rejected")
        self.state.log("trade", f"rejected trade #{trade_id}", trade_id=trade_id)
        return self.state.get_trade(trade_id)

    # -- position helpers --------------------------------------------------
    def close_position(self, ticker: str, price: float, mode: str = "paper") -> Optional[dict]:
        pos = {p["ticker"]: p for p in self.state.positions()}.get(ticker)
        if not pos or pos["quantity"] <= 0:
            return None
        return self.submit(ticker, "SELL", pos["quantity"], price, mode,
                           rationale="close position")

    def mark_to_market(self, prices: dict[str, float]) -> float:
        """Record an equity snapshot given current prices per ticker."""
        holdings = 0.0
        for pos in self.state.positions():
            holdings += pos["quantity"] * prices.get(pos["ticker"], pos["avg_price"])
        equity = self.cash + holdings
        self.state.record_equity(equity, self.cash)
        return equity

    # -- internals ---------------------------------------------------------
    def _fill(self, trade_id: int, ticker: str, side: str, qty: float, price: float) -> None:
        fee = price * qty * self.fee
        positions = {p["ticker"]: p for p in self.state.positions()}
        pos = positions.get(ticker, {"quantity": 0.0, "avg_price": 0.0})

        if side == "BUY":
            cost = price * qty + fee
            if cost > self.cash + 1e-9:
                self.state.set_trade_status(trade_id, "rejected")
                self.state.log("trade", f"trade #{trade_id} rejected: insufficient cash")
                return
            new_qty = pos["quantity"] + qty
            new_avg = (pos["avg_price"] * pos["quantity"] + price * qty) / new_qty
            self.cash = self.cash - cost
            self.state.upsert_position(ticker, new_qty, new_avg)
        else:  # SELL
            if qty > pos["quantity"] + 1e-9:
                self.state.set_trade_status(trade_id, "rejected")
                self.state.log("trade", f"trade #{trade_id} rejected: insufficient holdings")
                return
            self.cash = self.cash + price * qty - fee
            remaining = pos["quantity"] - qty
            self.state.upsert_position(
                ticker, remaining, pos["avg_price"] if remaining > 1e-12 else 0.0
            )

        self.state.set_trade_status(trade_id, "filled")
        self.mark_to_market({ticker: price})

    def _place_live_order(self, trade: dict) -> None:
        """Place a real order on the configured exchange. Only reached when allowed+approved.

        The venue is read from the ``exchange`` setting (default ``binance``).
        Native adapters (upbit/bithumb/kis) load their own API keys from the
        environment; ccxt venues take ``<NAME>_API_KEY`` / ``<NAME>_SECRET_KEY``.
        """
        from yammyquant.exchanges import NATIVE, get_exchange

        name = self.state.get("exchange", "binance")
        if name in NATIVE:
            adapter = get_exchange(name)
        else:
            adapter = get_exchange(
                name,
                api_key=os.getenv(f"{name.upper()}_API_KEY"),
                secret_key=os.getenv(f"{name.upper()}_SECRET_KEY"),
            )
        adapter.create_order(
            ticker=trade["ticker"], side=trade["side"],
            quantity=trade["quantity"], price=trade.get("price"),
            order_type="market",
        )
