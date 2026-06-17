"""Performance metrics computed from an equity curve and trade log."""

from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd

# Approximate number of bars per year, used to annualize Sharpe/CAGR.
_BARS_PER_YEAR = {
    "1m": 525_600, "3m": 175_200, "5m": 105_120, "15m": 35_040, "30m": 17_520,
    "1h": 8_760, "2h": 4_380, "4h": 2_190, "6h": 1_460, "8h": 1_095, "12h": 730,
    "1d": 365, "1w": 52, "1M": 12,
}


def max_drawdown(equity: pd.Series) -> float:
    """Largest peak-to-trough decline as a negative fraction (e.g. -0.23)."""
    if equity.empty:
        return 0.0
    running_max = equity.cummax()
    drawdown = equity / running_max - 1.0
    return float(drawdown.min())


def sharpe(returns: pd.Series, periods_per_year: float) -> float:
    """Annualized Sharpe ratio (risk-free rate assumed 0)."""
    if returns.std(ddof=0) == 0 or returns.empty:
        return 0.0
    return float(np.sqrt(periods_per_year) * returns.mean() / returns.std(ddof=0))


def summary(
    equity_curve: pd.DataFrame,
    trades: pd.DataFrame,
    interval: Optional[str] = None,
) -> dict:
    """Summarize a run into a dict of headline statistics."""
    if equity_curve is None or equity_curve.empty:
        return {"bars": 0, "total_return": 0.0}

    equity = equity_curve["equity"]
    start, end = float(equity.iloc[0]), float(equity.iloc[-1])
    total_return = end / start - 1.0 if start else 0.0

    returns = equity.pct_change().dropna()
    ppy = _BARS_PER_YEAR.get(interval or "", 252)
    n_years = len(equity) / ppy if ppy else 0
    cagr = (end / start) ** (1 / n_years) - 1.0 if start and n_years > 0 else 0.0

    closed = trades[trades["action"] == "SELL"] if not trades.empty else trades
    wins = int((closed["realized_pnl"] > 0).sum()) if not closed.empty else 0
    n_closed = len(closed)
    gross_win = float(closed.loc[closed["realized_pnl"] > 0, "realized_pnl"].sum()) if n_closed else 0.0
    gross_loss = float(-closed.loc[closed["realized_pnl"] < 0, "realized_pnl"].sum()) if n_closed else 0.0

    return {
        "bars": len(equity),
        "start_equity": round(start, 2),
        "end_equity": round(end, 2),
        "total_return": round(total_return, 4),
        "cagr": round(cagr, 4),
        "sharpe": round(sharpe(returns, ppy), 3),
        "max_drawdown": round(max_drawdown(equity), 4),
        "num_trades": int(len(trades)),
        "num_closed": n_closed,
        "win_rate": round(wins / n_closed, 4) if n_closed else 0.0,
        "profit_factor": round(gross_win / gross_loss, 3) if gross_loss else float("inf"),
    }
