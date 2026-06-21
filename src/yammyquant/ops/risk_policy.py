"""Account-level risk policy — enforced at order time (paper *and* live).

The backtest ``RiskConfig`` shapes a strategy's behavior; this is the operator's
seatbelt for the *live account*: hard limits checked on every order so a bad
signal — or a bug, or the operator — cannot blow up the book. The policy lives in
the shared state (``risk_policy`` setting), so it's set once and applies
everywhere; manage it with ``yq risk``.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Optional

from yammyquant.state.store import LiveState

_SETTING = "risk_policy"
_PROTECT_SETTING = "protect_policy"


@dataclass
class ProtectPolicy:
    """Protective-exit policy for *live/paper* open positions.

    The backtest ``RiskConfig`` applies stops inside a simulation; this carries
    the same idea to the live book — checked each cycle (or via ``yq protect``)
    against the latest mark. All fractions of the entry/peak; ``None`` disables.
    """

    stop_loss: Optional[float] = None       # exit if price falls this fraction below entry
    take_profit: Optional[float] = None     # exit if price rises this fraction above entry
    trailing_stop: Optional[float] = None   # exit on this give-back from the peak since entry

    @property
    def active(self) -> bool:
        return any(v is not None for v in (self.stop_loss, self.take_profit, self.trailing_stop))

    @classmethod
    def load(cls, state: LiveState) -> "ProtectPolicy":
        return cls(**(state.get(_PROTECT_SETTING) or {}))

    def save(self, state: LiveState) -> None:
        state.set(_PROTECT_SETTING, asdict(self))


@dataclass
class AccountRiskPolicy:
    max_order_value: Optional[float] = None      # cap notional per order
    max_position_value: Optional[float] = None   # cap total value held in one symbol
    max_open_positions: Optional[int] = None     # cap number of distinct holdings
    max_symbol_weight: Optional[float] = None    # cap one symbol as fraction of equity (0-1)
    daily_loss_limit: Optional[float] = None     # halt buys after this realized loss today
    cooldown_minutes: Optional[float] = None     # min minutes between trades on a symbol

    @classmethod
    def load(cls, state: LiveState) -> "AccountRiskPolicy":
        return cls(**(state.get(_SETTING) or {}))

    def save(self, state: LiveState) -> None:
        state.set(_SETTING, asdict(self))


def _today_realized(state: LiveState) -> float:
    today = datetime.now(timezone.utc).date().isoformat()
    return sum(
        float(t.get("meta", {}).get("realized", 0.0)) if isinstance(t.get("meta"), dict) else 0.0
        for t in state.trades(limit=500)
        if t["status"] == "filled" and (t["ts"] or "").startswith(today)
    )


def check_order(
    state: LiveState,
    ticker: str,
    side: str,
    quantity: float,
    price: float,
    equity: float,
) -> Optional[str]:
    """Return a rejection reason if the order violates policy, else ``None``.

    Sells are always allowed (reducing risk); limits gate buys/entries.
    """
    if side.upper() != "BUY":
        return None
    p = AccountRiskPolicy.load(state)
    order_value = price * quantity
    positions = {pos["ticker"]: pos for pos in state.positions()}
    pos = positions.get(ticker)

    if p.max_order_value is not None and order_value > p.max_order_value:
        return f"order value {order_value:.2f} exceeds max_order_value {p.max_order_value}"

    if p.max_position_value is not None:
        held = (pos["quantity"] * price) if pos else 0.0
        if held + order_value > p.max_position_value:
            return f"position value would exceed max_position_value {p.max_position_value}"

    if p.max_symbol_weight is not None and equity > 0:
        held = (pos["quantity"] * price) if pos else 0.0
        if (held + order_value) / equity > p.max_symbol_weight:
            return f"symbol weight would exceed max_symbol_weight {p.max_symbol_weight}"

    if p.max_open_positions is not None and ticker not in positions:
        if len(positions) >= p.max_open_positions:
            return f"already at max_open_positions {p.max_open_positions}"

    if p.daily_loss_limit is not None:
        realized = _today_realized(state)
        if realized <= -abs(p.daily_loss_limit):
            return f"daily loss limit hit ({realized:.2f} <= -{abs(p.daily_loss_limit)})"

    if p.cooldown_minutes is not None:
        for t in state.trades(limit=50):
            if t["ticker"] == ticker and t["status"] == "filled" and t["ts"]:
                last = datetime.fromisoformat(t["ts"])
                age_min = (datetime.now(timezone.utc) - last).total_seconds() / 60
                if age_min < p.cooldown_minutes:
                    return f"cooldown active on {ticker} ({age_min:.1f} < {p.cooldown_minutes} min)"
                break
    return None
