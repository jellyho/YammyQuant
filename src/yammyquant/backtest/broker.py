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

    def __init__(self, fee: float = 0.001, slippage: float = 0.0):
        self.fee = float(fee)
        self.slippage = float(slippage)

    def execute(self, order: Order, ref_price: float, time: datetime) -> Optional[Fill]:
        if order.action == Action.HOLD or order.quantity <= 0:
            return None
        price = order.price if order.price is not None else ref_price
        if order.action == Action.BUY:
            fill_price = price * (1 + self.slippage)
        else:
            fill_price = price * (1 - self.slippage)
        fee = fill_price * order.quantity * self.fee
        return Fill(
            order=order,
            fill_price=fill_price,
            fill_quantity=order.quantity,
            fee=fee,
            time=time,
        )
