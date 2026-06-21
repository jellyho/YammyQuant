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


def sortino(returns: pd.Series, periods_per_year: float) -> float:
    """Annualized Sortino ratio — like Sharpe but penalizes only downside vol."""
    if returns.empty:
        return 0.0
    downside = returns[returns < 0]
    dd = downside.std(ddof=0)
    if dd == 0 or np.isnan(dd):
        return 0.0
    return float(np.sqrt(periods_per_year) * returns.mean() / dd)


def calmar(cagr: float, max_dd: float) -> float:
    """CAGR divided by the magnitude of max drawdown."""
    return float(cagr / abs(max_dd)) if max_dd else 0.0


def expectancy(pnl: pd.Series) -> float:
    """Expected PnL per closed trade — the headline "is this edge positive?" stat.

    `win_rate * avg_win + loss_rate * avg_loss` over the realized-PnL series.
    Positive means the average trade makes money; algebraically equal to the
    mean of `pnl`, but expressed via the win/loss decomposition traders reason
    about. Returns 0.0 for an empty series.
    """
    if pnl is None or len(pnl) == 0:
        return 0.0
    return float(pnl.mean())


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
    mdd = max_drawdown(equity)
    ann_vol = float(returns.std(ddof=0) * np.sqrt(ppy)) if not returns.empty else 0.0

    if trades.empty:
        closed = trades
    elif "closing" in trades.columns:
        closed = trades[trades["closing"]]            # signed-position aware (longs + short covers)
    else:
        closed = trades[trades["action"] == "SELL"]   # legacy long-only trade logs
    pnl = closed["realized_pnl"] if not closed.empty else pd.Series(dtype=float)
    wins = pnl[pnl > 0]
    losses = pnl[pnl < 0]
    n_closed = len(closed)
    gross_win = float(wins.sum()) if n_closed else 0.0
    gross_loss = float(-losses.sum()) if n_closed else 0.0

    return {
        "bars": len(equity),
        "start_equity": round(start, 2),
        "end_equity": round(end, 2),
        "total_return": round(total_return, 4),
        "cagr": round(cagr, 4),
        "annual_volatility": round(ann_vol, 4),
        "sharpe": round(sharpe(returns, ppy), 3),
        "sortino": round(sortino(returns, ppy), 3),
        "calmar": round(calmar(cagr, mdd), 3),
        "max_drawdown": round(mdd, 4),
        "num_trades": int(len(trades)),
        "num_closed": n_closed,
        "win_rate": round(len(wins) / n_closed, 4) if n_closed else 0.0,
        # None (not inf) when there are no losing trades — keeps the value JSON-safe
        "profit_factor": round(gross_win / gross_loss, 3) if gross_loss else None,
        "avg_win": round(float(wins.mean()), 4) if len(wins) else 0.0,
        "avg_loss": round(float(losses.mean()), 4) if len(losses) else 0.0,
        "expectancy": round(expectancy(pnl), 4) if n_closed else 0.0,
        "best_trade": round(float(pnl.max()), 4) if n_closed else 0.0,
        "worst_trade": round(float(pnl.min()), 4) if n_closed else 0.0,
    }
