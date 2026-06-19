"""Order, Action and Fill value objects."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class Action(str, Enum):
    """Trade actions. ``str`` mixin so values serialize cleanly to CSV/JSON."""

    HOLD = "HOLD"
    BUY = "BUY"
    SELL = "SELL"


@dataclass(slots=True)
class Order:
    """A trade instruction emitted by a strategy.

    ``quantity`` is expressed in base-asset units. ``price`` is the strategy's
    intended/limit price; the broker decides the actual fill price.
    """

    action: Action
    ticker: str
    quantity: float = 0.0
    price: Optional[float] = None
    time: Optional[datetime] = None

    def __post_init__(self):
        if self.quantity < 0:
            raise ValueError("Order.quantity must be non-negative; use Action to set side.")


@dataclass(slots=True)
class Fill:
    """The realized result of an executed order."""

    order: Order
    fill_price: float
    fill_quantity: float
    fee: float = 0.0
    time: Optional[datetime] = None
    id: Optional[str] = field(default=None)

    @property
    def action(self) -> Action:
        return self.order.action

    @property
    def ticker(self) -> str:
        return self.order.ticker
