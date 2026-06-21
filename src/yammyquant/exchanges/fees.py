"""Per-exchange trading-fee schedules (maker / taker), as fractions of notional.

Real venues charge different fees for *maker* (resting limit that adds liquidity)
and *taker* (market / liquidity-removing) orders — and scalpers live or die by
them. These are sane published spot defaults; the live adapters can override
``Exchange.fees()`` to pull the account's actual tier from the API. Pick an
exchange and the backtest applies its fees automatically.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FeeSchedule:
    maker: float
    taker: float

    def rate(self, order_type: str) -> float:
        """Fee for an order type: limit rests (maker), market/stop crosses (taker)."""
        return self.maker if str(order_type).lower() == "limit" else self.taker


# published spot defaults (fractions); KR stock venues approximate commission only
# (transaction tax on sells is venue/regulation-specific and not modeled here)
_DEFAULT = FeeSchedule(maker=0.001, taker=0.001)

FEE_SCHEDULE = {
    "binance": FeeSchedule(0.001, 0.001),     # 0.10% / 0.10%
    "upbit": FeeSchedule(0.0005, 0.0005),     # 0.05%
    "bithumb": FeeSchedule(0.0004, 0.0004),   # 0.04%
    "coinone": FeeSchedule(0.002, 0.002),     # 0.20%
    "korbit": FeeSchedule(0.0008, 0.0008),    # ~0.08%
    "kis": FeeSchedule(0.00015, 0.00015),     # 한국투자증권 ~0.015% commission
    "toss": FeeSchedule(0.00015, 0.00015),    # 토스증권 ~0.015% commission
}


def fee_schedule(exchange: str) -> FeeSchedule:
    """Maker/taker schedule for ``exchange`` (case-insensitive); default if unknown."""
    return FEE_SCHEDULE.get((exchange or "").lower(), _DEFAULT)
