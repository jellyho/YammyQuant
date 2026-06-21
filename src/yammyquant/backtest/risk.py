"""Risk management — position sizing, stop-loss / take-profit, drawdown kill switch.

Every serious framework (freqtrade's stoploss/protections, Jesse's risk rules,
the LLM "risk manager" agents) has an explicit risk layer; this is YammyQuant's.
It is engine-agnostic and unit-tested in isolation, then wired into
:class:`~yammyquant.backtest.engine.Backtest` via an optional ``risk=`` argument.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np


@dataclass
class RiskConfig:
    """Risk policy applied during a backtest / live run.

    Position sizing (applied to entry orders)
    -----------------------------------------
    - ``sizing="off"``        — use the order's own quantity (default)
    - ``sizing="fraction"``   — invest ``risk_fraction`` of equity per entry
    - ``sizing="volatility"`` — size so that ``vol_target`` (annualized) is met,
      using recent return volatility; caps at ``max_position_fraction``

    Protective exits (checked each bar against intrabar high/low)
    -------------------------------------------------------------
    - ``stop_loss``   — fractional loss from entry that forces an exit (0.05 = 5%)
    - ``take_profit`` — fractional gain from entry that forces an exit

    Kill switch
    -----------
    - ``max_drawdown`` — if equity draws down past this fraction, flatten and halt
    """

    sizing: str = "off"
    risk_fraction: float = 0.1
    vol_target: float = 0.5
    vol_lookback: int = 20
    max_position_fraction: float = 1.0
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    max_drawdown: Optional[float] = None


class RiskManager:
    """Applies a :class:`RiskConfig`. Pure functions over plain numbers."""

    def __init__(self, config: RiskConfig, periods_per_year: float = 365):
        self.config = config
        self.ppy = periods_per_year

    # -- position sizing ---------------------------------------------------
    def size_entry(self, equity: float, price: float,
                   recent_returns: Optional[np.ndarray] = None) -> float:
        """Quantity (base units) to buy for an entry, per the sizing policy."""
        c = self.config
        if c.sizing == "off" or price <= 0:
            return 0.0  # caller keeps the strategy's own quantity
        if c.sizing == "fraction":
            notional = equity * c.risk_fraction
        elif c.sizing == "volatility":
            vol = self._annualized_vol(recent_returns)
            scale = c.vol_target / vol if vol > 0 else c.max_position_fraction
            notional = equity * min(scale, c.max_position_fraction)
        else:
            raise ValueError(f"unknown sizing {c.sizing!r}")
        notional = min(notional, equity * c.max_position_fraction)
        return max(notional / price, 0.0)

    def _annualized_vol(self, recent_returns: Optional[np.ndarray]) -> float:
        if recent_returns is None or len(recent_returns) < 2:
            return 0.0
        return float(np.std(recent_returns, ddof=0) * np.sqrt(self.ppy))

    # -- protective exits --------------------------------------------------
    def exit_price(self, avg_entry: float, bar_high: float, bar_low: float,
                   is_short: bool = False) -> Optional[float]:
        """Return the fill price if a stop-loss/take-profit triggers this bar.

        Long: stop-loss checks the bar low, take-profit the bar high.
        Short (``is_short=True``): the sides invert — a loss is price rising, so
        the stop sits *above* entry and checks the bar high, while the profit
        target sits *below* and checks the bar low.
        Stop-loss takes precedence (conservative) when both could trigger.
        """
        c = self.config
        if avg_entry <= 0:
            return None
        if not is_short:
            if c.stop_loss is not None and bar_low <= avg_entry * (1 - c.stop_loss):
                return avg_entry * (1 - c.stop_loss)
            if c.take_profit is not None and bar_high >= avg_entry * (1 + c.take_profit):
                return avg_entry * (1 + c.take_profit)
        else:
            if c.stop_loss is not None and bar_high >= avg_entry * (1 + c.stop_loss):
                return avg_entry * (1 + c.stop_loss)
            if c.take_profit is not None and bar_low <= avg_entry * (1 - c.take_profit):
                return avg_entry * (1 - c.take_profit)
        return None

    # -- kill switch -------------------------------------------------------
    def drawdown_breached(self, peak_equity: float, equity: float) -> bool:
        c = self.config
        if c.max_drawdown is None or peak_equity <= 0:
            return False
        return (equity / peak_equity - 1.0) <= -abs(c.max_drawdown)
