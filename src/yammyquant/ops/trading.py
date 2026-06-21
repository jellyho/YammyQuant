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
    def __init__(self, state: LiveState, fee: float = 0.001, exchange: Optional[str] = None):
        self.state = state
        self.fee = fee
        self.exchange = exchange
        # when an exchange is given, paper/live fills cost that venue's real
        # maker/taker fees (so paper mirrors live); otherwise the flat ``fee``
        self._sched = None
        if exchange:
            from yammyquant.exchanges.fees import fee_schedule
            self._sched = fee_schedule(exchange)

    def _fee_rate(self, order_type: str = "market") -> float:
        return self._sched.rate(order_type) if self._sched else self.fee

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
        order_type: str = "market",
        context: Optional[dict] = None,
    ) -> dict:
        """Submit an order. Paper fills now; live is queued for approval.

        The account-level risk policy is checked first and applies to both modes.
        ``order_type`` is ``"market"`` or ``"limit"`` — limit live orders rest as
        ``submitted`` after placement until ``sync_orders`` settles them.
        ``context`` is an optional structured rationale (contributing strategies,
        ensemble score, sentiment, sizing) — stored on the trade and surfaced in
        the notification so the human sees *why* a trade happened.
        """
        side = side.upper()
        if side not in ("BUY", "SELL"):
            raise ValueError("side must be BUY or SELL")
        if quantity <= 0:
            raise ValueError("quantity must be positive")

        meta = {"order_type": order_type}
        if context:
            meta["decision"] = context

        reason = self._risk_check(ticker, side, quantity, price)
        if reason is not None:
            trade_id = self.state.add_trade(ticker, side, quantity, price, mode, "rejected",
                                            rationale, **meta)
            self.state.log("trade", f"risk policy blocked #{trade_id}: {reason}", trade_id=trade_id)
            trade = self.state.get_trade(trade_id)
            self._notify_trade(trade, context, headline=f"🚫 risk policy blocked — {reason}",
                               level="warn")
            return trade

        if mode == "live":
            trade_id = self.state.add_trade(
                ticker, side, quantity, price, "live", "pending", rationale, **meta
            )
            self.state.log(
                "trade",
                f"LIVE {order_type} {side} {quantity} {ticker} @ {price} queued for approval (#{trade_id})",
                trade_id=trade_id,
            )
            trade = self.state.get_trade(trade_id)
            self._notify_trade(trade, context,
                               headline=f"⏳ LIVE order needs approval — `yq approve {trade_id}`",
                               level="action")
            return trade

        # paper: fill immediately
        trade_id = self.state.add_trade(
            ticker, side, quantity, price, "paper", "pending", rationale, **meta
        )
        self._fill(trade_id, ticker, side, quantity, price, order_type)
        trade = self.state.get_trade(trade_id)
        filled = trade["status"] == "filled"
        self._notify_trade(
            trade, context,
            headline="✅ paper fill" if filled else "❌ paper order rejected (insufficient funds/holdings)",
            level="info" if filled else "warn")
        return trade

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
            result = placer(trade)
            if isinstance(result, dict):
                oid = result.get("orderId") or result.get("id") or result.get("uuid")
                if oid is not None:
                    self.state.set_trade_meta(trade_id, exchange_order_id=str(oid))
            meta = trade.get("meta") if isinstance(trade.get("meta"), dict) else {}
            if meta.get("order_type") == "limit":
                # limit order rests at the exchange; settle later via sync_orders
                self.state.set_trade_status(trade_id, "submitted")
                self.state.log("trade", f"LIVE limit #{trade_id} submitted (awaiting fill)")
                return self.state.get_trade(trade_id)

        otype = (trade.get("meta") or {}).get("order_type", "market") \
            if isinstance(trade.get("meta"), dict) else "market"
        self._fill(trade_id, trade["ticker"], trade["side"],
                   trade["quantity"], trade["price"], otype)
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
    def _apply(self, ticker: str, side: str, qty: float, price: float,
               order_type: str = "market"):
        """Apply a fill to cash + position. Returns (ok, realized_pnl)."""
        fee = price * qty * self._fee_rate(order_type)
        pos = {p["ticker"]: p for p in self.state.positions()}.get(
            ticker, {"quantity": 0.0, "avg_price": 0.0})
        if side == "BUY":
            cost = price * qty + fee
            if cost > self.cash + 1e-9:
                return False, 0.0
            new_qty = pos["quantity"] + qty
            self.cash = self.cash - cost
            self.state.upsert_position(
                ticker, new_qty, (pos["avg_price"] * pos["quantity"] + price * qty) / new_qty)
            return True, 0.0
        if qty > pos["quantity"] + 1e-9:
            return False, 0.0
        self.cash = self.cash + price * qty - fee
        realized = (price - pos["avg_price"]) * qty - fee
        remaining = pos["quantity"] - qty
        self.state.upsert_position(ticker, remaining, pos["avg_price"] if remaining > 1e-12 else 0.0)
        return True, realized

    def _fill(self, trade_id: int, ticker: str, side: str, qty: float, price: float,
              order_type: str = "market") -> None:
        ok, realized = self._apply(ticker, side, qty, price, order_type)
        if not ok:
            self.state.set_trade_status(trade_id, "rejected")
            self.state.log("trade", f"trade #{trade_id} rejected: insufficient funds/holdings")
            return
        if side == "SELL":
            self.state.record_realized(trade_id, realized)
        self.state.set_trade_status(trade_id, "filled")
        self.mark_to_market({ticker: price})

    def _fill_partial(self, trade: dict, qty: float) -> None:
        """Apply a partial fill (delta qty) without closing the order."""
        otype = (trade.get("meta") or {}).get("order_type", "market") \
            if isinstance(trade.get("meta"), dict) else "market"
        ok, realized = self._apply(trade["ticker"], trade["side"], qty, trade["price"], otype)
        if ok and trade["side"] == "SELL":
            prev = (trade.get("meta") or {}).get("realized", 0.0) if isinstance(trade.get("meta"), dict) else 0.0
            self.state.set_trade_meta(trade["id"], realized=prev + realized)
        if ok:
            self.mark_to_market({trade["ticker"]: trade["price"]})

    # -- risk + notifications ---------------------------------------------
    def _equity_estimate(self) -> float:
        holdings = sum(p["quantity"] * p["avg_price"] for p in self.state.positions())
        return self.cash + holdings

    def _risk_check(self, ticker: str, side: str, quantity: float, price: float):
        from yammyquant.ops.risk_policy import check_order
        return check_order(self.state, ticker, side, quantity, price, self._equity_estimate())

    def _notify(self, message: str, level: str = "info") -> None:
        from yammyquant.ops.notify import notify
        notify(self.state, message, level)

    def _notify_trade(self, trade: dict, context: Optional[dict], headline: str,
                      level: str = "info") -> None:
        """Send an information-rich trade alert: what, how big, and *why*."""
        side = trade.get("side", "")
        emoji = "🟢" if side == "BUY" else "🔴" if side == "SELL" else "•"
        price = trade.get("price") or 0
        qty = trade.get("quantity") or 0
        notional = price * qty
        lines = [
            headline,
            f"{emoji} {trade.get('mode', '').upper()} {side} {qty} {trade.get('ticker')} "
            f"@ {price} (≈{notional:,.0f})",
        ]
        if trade.get("rationale"):
            lines.append(f"↳ {trade['rationale']}")
        ctx = context or {}
        voters = ctx.get("voters")
        if voters:
            lines.append("voters: " + " · ".join(f"{k}={v}" for k, v in voters.items()))
        facts = []
        for key in ("rule", "score", "sentiment", "weight", "equity"):
            if ctx.get(key) is not None:
                facts.append(f"{key} {ctx[key]}")
        if facts:
            lines.append(" · ".join(facts))
        self._notify("\n".join(lines), level)

    def _place_live_order(self, trade: dict) -> None:
        """Place a real order on the configured exchange. Only reached when allowed+approved.

        The venue is the ``exchange`` cockpit setting, falling back to the central
        config's default. All credentials are resolved centrally by
        :func:`yammyquant.exchanges.get_exchange` — no per-venue handling here.
        """
        from yammyquant.exchanges import get_exchange, default_exchange

        name = self.state.get("exchange") or default_exchange()
        meta = trade.get("meta") if isinstance(trade.get("meta"), dict) else {}
        return get_exchange(name).create_order(
            ticker=trade["ticker"], side=trade["side"],
            quantity=trade["quantity"], price=trade.get("price"),
            order_type=meta.get("order_type", "market"),
        )
