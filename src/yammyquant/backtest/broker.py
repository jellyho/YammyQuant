"""Brokers: turn :class:`Order` instructions into :class:`Fill` results.

The broker is the single seam between simulation and reality. A backtest uses
:class:`BacktestBroker` (fills against historical prices with slippage + fee);
live trading swaps in a real-exchange broker exposing the same ``execute`` API.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Optional

from yammyquant.backtest.order import Action, Fill, Order


class Broker(ABC):
    @abstractmethod
    def execute(self, order: Order, ref_price: float, time: datetime) -> Optional[Fill]:
        """Execute ``order``; return a :class:`Fill` or ``None`` if not filled."""


class BacktestBroker(Broker):
    """Simulated broker.

    Parameters
    ----------
    fee:
        Proportional fee charged on notional (e.g. ``0.001``).
    slippage:
        Proportional adverse price move applied on fills (e.g. ``0.0005``).
        Buys fill slightly higher, sells slightly lower.
    """

    def __init__(self, fee: float = 0.001, slippage: float = 0.0,
                 maker_fee: Optional[float] = None, taker_fee: Optional[float] = None):
        self.fee = float(fee)
        self.slippage = float(slippage)
        # when set, charge maker on resting limits and taker on market/stop fills
        self.maker_fee = float(maker_fee) if maker_fee is not None else None
        self.taker_fee = float(taker_fee) if taker_fee is not None else None

    def _rate(self, order: Order) -> float:
        """Fee rate for an order: maker for a resting LIMIT, taker otherwise."""
        if self.maker_fee is None and self.taker_fee is None:
            return self.fee
        from yammyquant.backtest.order import OrderType
        if order.type == OrderType.LIMIT:
            return self.maker_fee if self.maker_fee is not None else self.fee
        return self.taker_fee if self.taker_fee is not None else self.fee

    def execute(self, order: Order, ref_price: float, time: datetime) -> Optional[Fill]:
        """Fill a MARKET order at the engine-provided ``ref_price``.

        ``ref_price`` (the bar's open under next-open timing, or its close in
        legacy mode) is authoritative — the order's own ``price`` is advisory and
        ignored here, so realistic fill timing actually takes effect.
        """
        if order.action == Action.HOLD or order.quantity <= 0:
            return None
        return self.make_fill(order, ref_price, time)

    def _slipped(self, order: Order, price: float) -> float:
        """Apply slippage to crossing (taker) fills only.

        A resting LIMIT fills at its price (maker) and is not slipped — mirroring
        the paper broker. MARKET and triggered STOP orders cross the book (taker)
        and pay slippage: buys fill higher, sells lower.
        """
        from yammyquant.backtest.order import OrderType
        if self.slippage <= 0 or order.type == OrderType.LIMIT:
            return price
        return price * (1 + self.slippage) if order.action == Action.BUY \
            else price * (1 - self.slippage)

    def make_fill(self, order: Order, price: float, time: datetime) -> Optional[Fill]:
        """Build a slippage- and fee-adjusted :class:`Fill` at ``price``.

        Shared by market fills and by the engine's resting limit/stop fills.
        """
        if order.action == Action.HOLD or order.quantity <= 0:
            return None
        fill_price = self._slipped(order, price)
        fee = fill_price * order.quantity * self._rate(order)
        return Fill(order=order, fill_price=fill_price, fill_quantity=order.quantity,
                    fee=fee, time=time)
