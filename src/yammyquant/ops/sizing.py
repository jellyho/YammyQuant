"""Position sizing for live decisions.

`decide` sizes an entry to a fraction of equity. The method is chosen by the
``sizing`` setting:

- ``fixed``      — ``weight`` of equity (the default).
- ``volatility`` — scale *down* from ``weight`` when recent realized volatility
  exceeds ``target_vol`` (volatility targeting); never scales above ``weight``.
- ``kelly``      — a capped Kelly fraction from the realized win/loss record,
  capped by ``weight``.

All methods are pure and return a quantity (units), so they're easy to test.
"""

from __future__ import annotations

from typing import Optional


def _realized_vol(candle, window: int = 20) -> float:
    import pandas as pd

    close = pd.Series(candle.close, dtype=float)
    rets = close.pct_change().dropna()
    if len(rets) < 2:
        return 0.0
    return float(rets.tail(window).std()) * (252 ** 0.5)


def kelly_fraction(trades, cap: float = 0.25) -> float:
    """Capped Kelly fraction from closed trades' realized PnL."""
    closed = [float(t["realized_pnl"]) for t in trades
              if t.get("status") == "filled" and t.get("realized_pnl") is not None]
    wins = [x for x in closed if x > 0]
    losses = [-x for x in closed if x < 0]
    if not wins or not losses:
        return 0.0
    p = len(wins) / (len(wins) + len(losses))
    avg_win = sum(wins) / len(wins)
    avg_loss = sum(losses) / len(losses)
    b = avg_win / avg_loss if avg_loss else 0.0
    if b <= 0:
        return 0.0
    frac = p - (1 - p) / b          # f* = p - q/b
    return round(max(0.0, min(cap, frac)), 4)


def position_size(method: str, equity: float, price: float, weight: float,
                  candle=None, trades: Optional[list] = None,
                  target_vol: float = 0.5, kelly_cap: float = 0.25) -> float:
    """Return the quantity to buy under the chosen sizing method."""
    if price <= 0 or equity <= 0 or weight <= 0:
        return 0.0
    method = (method or "fixed").lower()
    frac = weight
    if method == "volatility" and candle is not None:
        rv = _realized_vol(candle)
        if rv > 0:
            frac = min(weight, weight * (target_vol / rv))   # only de-risk in high vol
    elif method == "kelly":
        frac = min(weight, kelly_fraction(trades or [], kelly_cap))
    return round(max(0.0, frac) * equity / price, 8)
