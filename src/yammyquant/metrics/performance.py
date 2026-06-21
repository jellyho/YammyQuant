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


def _phi(x: float) -> float:
    """Standard normal CDF (no scipy dependency)."""
    import math
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def probabilistic_sharpe_ratio(returns: pd.Series, sr_benchmark: float = 0.0) -> float:
    """Probability the *true* Sharpe exceeds ``sr_benchmark`` (Bailey & López de Prado).

    Works on per-period (non-annualized) returns and corrects the naive Sharpe
    for sample length, skew and kurtosis — short, fat-tailed, negatively-skewed
    records get penalized. ``sr_benchmark`` is a per-period Sharpe (0 = "is the
    edge positive at all?"). Returns a probability in [0, 1].
    """
    r = pd.Series(returns).dropna()
    n = len(r)
    sd = r.std(ddof=1)
    if n < 3 or sd == 0 or np.isnan(sd):
        return 0.0
    sr = r.mean() / sd                                   # per-period Sharpe
    skew = float(r.skew())
    # pandas kurt() is already excess kurtosis (normal -> 0); PSR wants raw kurtosis
    kurt = float(r.kurt()) + 3.0
    denom = np.sqrt(1.0 - skew * sr + (kurt - 1.0) / 4.0 * sr ** 2)
    if denom == 0 or np.isnan(denom):
        return 0.0
    z = (sr - sr_benchmark) * np.sqrt(n - 1) / denom
    return round(float(_phi(z)), 4)


def bootstrap_sharpe_ci(returns: pd.Series, periods_per_year: float,
                        n_boot: int = 1000, alpha: float = 0.05,
                        seed: Optional[int] = 0) -> dict:
    """Bootstrap confidence interval + p-value for the annualized Sharpe.

    Resamples the return series with replacement ``n_boot`` times, recomputing
    Sharpe each time, and returns the ``(alpha/2, 1-alpha/2)`` percentile band
    plus ``p_value`` = the fraction of resamples with Sharpe ≤ 0 (a one-sided
    "could this be noise?" estimate).
    """
    r = pd.Series(returns).dropna().to_numpy()
    out = {"sharpe_ci_low": 0.0, "sharpe_ci_high": 0.0, "sharpe_p_value": 1.0,
           "n_boot": int(n_boot)}
    if len(r) < 3:
        return out
    rng = np.random.default_rng(seed)
    scale = np.sqrt(periods_per_year)
    samples = np.empty(n_boot)
    for i in range(n_boot):
        draw = rng.choice(r, size=len(r), replace=True)
        sd = draw.std(ddof=0)
        samples[i] = scale * draw.mean() / sd if sd > 0 else 0.0
    lo, hi = np.percentile(samples, [100 * alpha / 2, 100 * (1 - alpha / 2)])
    out.update(sharpe_ci_low=round(float(lo), 3), sharpe_ci_high=round(float(hi), 3),
               sharpe_p_value=round(float(np.mean(samples <= 0)), 4))
    return out


def deflated_sharpe_ratio(returns: pd.Series, trial_sharpes: list,
                          periods_per_year: float) -> float:
    """Probability the best of ``N`` trials is genuinely > 0 (Bailey & López de Prado).

    When you search many parameter sets, the best Sharpe is inflated by luck. The
    DSR is the PSR evaluated against the *expected maximum* Sharpe under the null
    of no skill, given the number of trials and the spread of their Sharpes — so
    it deflates the winner by how hard you looked. Returns a probability in
    [0, 1]; well below 0.95 means the "best" params are likely overfit.
    """
    import math
    from statistics import NormalDist

    sr = [float(s) for s in trial_sharpes if s is not None and not np.isnan(s)]
    n = len(sr)
    if n < 2:
        return probabilistic_sharpe_ratio(returns)
    pp = [s / np.sqrt(periods_per_year) for s in sr]      # per-period Sharpes
    sd = float(np.std(pp, ddof=1))
    if sd == 0:
        return probabilistic_sharpe_ratio(returns)
    gamma = 0.5772156649015329                             # Euler–Mascheroni
    nd = NormalDist()
    e_max = sd * ((1 - gamma) * nd.inv_cdf(1 - 1.0 / n)
                  + gamma * nd.inv_cdf(1 - 1.0 / (n * math.e)))
    return probabilistic_sharpe_ratio(returns, sr_benchmark=e_max)


def value_at_risk(returns: pd.Series, alpha: float = 0.05) -> float:
    """Historical Value-at-Risk: the per-bar loss not exceeded with ``1-alpha``
    confidence, as a positive magnitude (VaR 95% → ``alpha=0.05``)."""
    r = pd.Series(returns).dropna()
    if r.empty:
        return 0.0
    q = float(np.quantile(r, alpha))
    return round(-q, 6)


def expected_shortfall(returns: pd.Series, alpha: float = 0.05) -> float:
    """Conditional VaR / expected shortfall: the mean per-bar loss in the worst
    ``alpha`` tail, as a positive magnitude — how bad the bad days actually are."""
    r = pd.Series(returns).dropna()
    if r.empty:
        return 0.0
    q = float(np.quantile(r, alpha))
    tail = r[r <= q]
    if tail.empty:
        return round(-q, 6)
    return round(-float(tail.mean()), 6)


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


def trade_analytics(equity_curve: pd.DataFrame, trades: pd.DataFrame) -> dict:
    """Trade-level analytics: holding period, win/loss streaks, exposure, turnover.

    - ``avg_holding_bars`` — mean bars held per round-trip (entry until flat).
    - ``max_consecutive_wins`` / ``max_consecutive_losses`` — longest streaks of
      winning / losing closes (psychological + risk-of-ruin relevance).
    - ``exposure`` — fraction of bars with an open position (time in market).
    - ``turnover`` — total traded notional relative to ending equity.
    """
    out = {"avg_holding_bars": None, "max_consecutive_wins": 0,
           "max_consecutive_losses": 0, "exposure": 0.0, "turnover": 0.0}
    if (equity_curve is None or equity_curve.empty
            or trades is None or trades.empty):
        return out

    n_bars = len(equity_curve)
    pos_of = {t: k for k, t in enumerate(equity_curve.index)}

    # round-trips from position_qty transitions through zero
    holding, in_bars, entry_bar = [], 0, None
    for _, row in trades.iterrows():
        bar = pos_of.get(row["time"])
        if bar is None:
            continue
        open_after = abs(float(row.get("position_qty", 0.0) or 0.0)) > 1e-12
        if entry_bar is None and open_after:
            entry_bar = bar
        elif entry_bar is not None and not open_after:
            holding.append(bar - entry_bar)
            in_bars += bar - entry_bar
            entry_bar = None
    if entry_bar is not None:                       # still open at the end
        in_bars += (n_bars - 1) - entry_bar

    # win/loss streaks over closing trades
    closes = trades[trades["closing"]] if "closing" in trades.columns \
        else trades[trades["action"] == "SELL"]
    sw = sl = mw = ml = 0
    for pnl in (closes["realized_pnl"] if not closes.empty else []):
        if pnl > 0:
            sw, sl = sw + 1, 0
        elif pnl < 0:
            sl, sw = sl + 1, 0
        else:
            sw = sl = 0
        mw, ml = max(mw, sw), max(ml, sl)

    notional = float((trades["price"] * trades["quantity"]).sum())
    end_eq = float(equity_curve["equity"].iloc[-1])
    out.update(
        avg_holding_bars=round(float(np.mean(holding)), 2) if holding else None,
        max_consecutive_wins=mw,
        max_consecutive_losses=ml,
        exposure=round(in_bars / n_bars, 4) if n_bars else 0.0,
        turnover=round(notional / end_eq, 3) if end_eq else 0.0,
    )
    return out


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

    stats = {
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
        "var_95": value_at_risk(returns, 0.05),
        "cvar_95": expected_shortfall(returns, 0.05),
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
    stats.update(trade_analytics(equity_curve, trades))
    return stats
