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
    - ``sizing="kelly"``      — size by the capped Kelly fraction from the realized
      record (``kelly_scale`` × full Kelly, e.g. 0.5 for half-Kelly); falls back
      to ``risk_fraction`` until ``kelly_min_trades`` closes exist

    Protective exits (checked each bar against intrabar high/low)
    -------------------------------------------------------------
    - ``stop_loss``   — fractional loss from entry that forces an exit (0.05 = 5%)
    - ``take_profit`` — fractional gain from entry that forces an exit
    - ``atr_stop`` / ``atr_take`` — volatility-scaled stop/take placed ``N × ATR``
      from the entry price (``atr_lookback`` bars). Adapts the stop distance to
      each market's noise instead of a flat percentage.
    - ``trailing_stop`` — fractional give-back from the best price seen since
      entry (the high-water mark) that forces an exit; locks in open profit as
      the trade runs
    - ``breakeven_trigger`` — once the trade gains this fraction, the stop ratchets
      up to the entry price (a free trade thereafter)
    - ``max_holding_bars`` — force an exit after holding this many bars (time stop)

    Kill switch
    -----------
    - ``max_drawdown`` — if equity draws down past this fraction, flatten and halt
    """

    sizing: str = "off"
    risk_fraction: float = 0.1
    vol_target: float = 0.5
    vol_lookback: int = 20
    kelly_scale: float = 1.0
    kelly_min_trades: int = 10
    max_position_fraction: float = 1.0
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    atr_stop: Optional[float] = None
    atr_take: Optional[float] = None
    atr_lookback: int = 14
    trailing_stop: Optional[float] = None
    breakeven_trigger: Optional[float] = None
    max_holding_bars: Optional[int] = None
    max_drawdown: Optional[float] = None


class RiskManager:
    """Applies a :class:`RiskConfig`. Pure functions over plain numbers."""

    def __init__(self, config: RiskConfig, periods_per_year: float = 365):
        self.config = config
        self.ppy = periods_per_year

    # -- position sizing ---------------------------------------------------
    def size_entry(self, equity: float, price: float,
                   recent_returns: Optional[np.ndarray] = None,
                   realized_pnls: Optional[np.ndarray] = None) -> float:
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
        elif c.sizing == "kelly":
            notional = equity * self.kelly_fraction(realized_pnls)
        else:
            raise ValueError(f"unknown sizing {c.sizing!r}")
        notional = min(notional, equity * c.max_position_fraction)
        return max(notional / price, 0.0)

    def kelly_fraction(self, realized_pnls: Optional[np.ndarray]) -> float:
        """Capped Kelly fraction from the realized record: ``W - (1-W)/R``.

        ``W`` is the win rate and ``R`` the payoff ratio (avg win / avg loss).
        Scaled by ``kelly_scale`` (e.g. 0.5 for half-Kelly) and clamped to
        ``[0, max_position_fraction]``. Until ``kelly_min_trades`` closed trades
        exist (or with no losses to anchor the ratio) it falls back to
        ``risk_fraction`` so early sizing isn't wild.
        """
        c = self.config
        pnls = np.asarray(realized_pnls, dtype=float) if realized_pnls is not None \
            else np.array([])
        if pnls.size < c.kelly_min_trades:
            return min(c.risk_fraction, c.max_position_fraction)
        wins, losses = pnls[pnls > 0], pnls[pnls < 0]
        if wins.size == 0 or losses.size == 0:
            return min(c.risk_fraction, c.max_position_fraction)
        win_rate = wins.size / pnls.size
        payoff = wins.mean() / abs(losses.mean())
        f = win_rate - (1 - win_rate) / payoff
        return float(min(max(f * c.kelly_scale, 0.0), c.max_position_fraction))

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

    def trailing_exit(self, hwm: float, bar_high: float, bar_low: float,
                      is_short: bool = False) -> Optional[float]:
        """Exit price if a trailing stop triggers, given the high-water mark.

        ``hwm`` is the most favorable price seen since entry — the running max
        for a long, the running min for a short. The stop trails ``trailing_stop``
        away from it; for a long it sits below the hwm (checks the bar low), for
        a short above it (checks the bar high).
        """
        c = self.config
        if c.trailing_stop is None or hwm <= 0:
            return None
        if is_short:
            stop = hwm * (1 + c.trailing_stop)
            return stop if bar_high >= stop else None
        stop = hwm * (1 - c.trailing_stop)
        return stop if bar_low <= stop else None

    def breakeven_exit(self, avg_entry: float, hwm: float, bar_high: float,
                       bar_low: float, is_short: bool = False) -> Optional[float]:
        """Exit at the entry price once the trade has gained ``breakeven_trigger``.

        The hwm crossing the trigger arms a breakeven stop at ``avg_entry``; the
        exit fires when price trades back to entry (bar low for a long, bar high
        for a short).
        """
        c = self.config
        if c.breakeven_trigger is None or avg_entry <= 0:
            return None
        if is_short:
            armed = hwm <= avg_entry * (1 - c.breakeven_trigger)
            return avg_entry if armed and bar_high >= avg_entry else None
        armed = hwm >= avg_entry * (1 + c.breakeven_trigger)
        return avg_entry if armed and bar_low <= avg_entry else None

    # -- kill switch -------------------------------------------------------
    def drawdown_breached(self, peak_equity: float, equity: float) -> bool:
        c = self.config
        if c.max_drawdown is None or peak_equity <= 0:
            return False
        return (equity / peak_equity - 1.0) <= -abs(c.max_drawdown)
