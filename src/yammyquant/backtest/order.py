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


class OrderType(str, Enum):
    """How an order fills.

    - ``MARKET`` — fills at the engine's reference price for the bar (the next
      bar's open under realistic fill timing).
    - ``LIMIT``  — rests until price reaches ``price`` or better (buy fills at/below,
      sell at/above).
    - ``STOP``   — rests until price trades through ``price`` (buy on a break up,
      sell on a break down), then fills like a market order.
    """

    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP = "STOP"


@dataclass(slots=True)
class Order:
    """A trade instruction emitted by a strategy.

    ``quantity`` is in base-asset units. For ``MARKET`` orders ``price`` is just
    the strategy's advisory price (the broker fills at the bar reference price);
    for ``LIMIT`` / ``STOP`` orders ``price`` is the trigger and is required.
    """

    action: Action
    ticker: str
    quantity: float = 0.0
    price: Optional[float] = None
    time: Optional[datetime] = None
    type: OrderType = OrderType.MARKET

    def __post_init__(self):
        if self.quantity < 0:
            raise ValueError("Order.quantity must be non-negative; use Action to set side.")
        if self.type in (OrderType.LIMIT, OrderType.STOP) and self.price is None:
            raise ValueError(f"{self.type.value} orders require a price.")


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
