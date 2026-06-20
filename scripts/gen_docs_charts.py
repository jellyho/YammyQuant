"""Generate the example charts shown in the documentation.

Produces real library output — runs actual backtests / indicators on a
deterministic synthetic price series and saves PNGs into ``docs/assets/``.
Re-run with:  python scripts/gen_docs_charts.py
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from yammyquant.data.candle import Candle  # noqa: E402
from yammyquant.backtest.engine import Backtest  # noqa: E402
from yammyquant.strategy.builtin import MACross, SuperTrendFollow, RSIReversion  # noqa: E402
from yammyquant.strategy.ensemble import Ensemble  # noqa: E402

ASSETS = Path(__file__).resolve().parent.parent / "docs" / "assets"
ASSETS.mkdir(parents=True, exist_ok=True)

# Plotly-cockpit-ish dark palette so the docs images match the dashboard.
BG, FG, GRID = "#0e1116", "#e6edf3", "#222a35"
ACCENT, GREEN, RED, AMBER = "#4da3ff", "#3fb950", "#f85149", "#d29922"
plt.rcParams.update({
    "figure.facecolor": BG, "axes.facecolor": BG, "savefig.facecolor": BG,
    "text.color": FG, "axes.labelcolor": FG, "axes.edgecolor": GRID,
    "xtick.color": FG, "ytick.color": FG, "grid.color": GRID,
    "axes.titlecolor": FG, "font.size": 10, "axes.grid": True,
    "grid.alpha": 0.4, "legend.framealpha": 0.0,
})


def make_candle(n: int = 400, seed: int = 7) -> Candle:
    """A realistic trending + mean-reverting price series (reproducible)."""
    rng = np.random.default_rng(seed)
    drift = np.concatenate([
        np.full(n // 2, 0.0009), np.full(n - n // 2, -0.0004)])  # bull then chop
    shocks = rng.normal(0, 0.018, n)
    cycle = 0.012 * np.sin(np.arange(n) / 13.0)
    rets = drift + shocks + cycle
    close = 100 * np.exp(np.cumsum(rets))
    high = close * (1 + rng.uniform(0.0, 0.012, n))
    low = close * (1 - rng.uniform(0.0, 0.012, n))
    open_ = np.concatenate([[close[0]], close[:-1]])
    vol = rng.uniform(800, 2200, n)
    idx = pd.date_range("2024-01-01", periods=n, freq="1D")
    df = pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close, "volume": vol}, index=idx)
    return Candle("BTCUSDT", df, interval="1d")


def _save(fig, name: str) -> None:
    fig.tight_layout()
    fig.savefig(ASSETS / name, dpi=130, bbox_inches="tight")
    plt.close(fig)
    print("wrote", ASSETS / name)


def chart_signals(candle: Candle) -> None:
    """Price + fast/slow MA with BUY/SELL markers from a macross backtest."""
    res = Backtest(candle, MACross(10, 30), cash=10_000, fee=0.001).run()
    close = pd.Series(candle.close, index=candle.index)
    fig, ax = plt.subplots(figsize=(10, 4.6))
    ax.plot(close.index, close, color=FG, lw=1.3, label="close")
    ax.plot(close.index, candle.ind.sma(10), color=ACCENT, lw=1.0, label="SMA 10")
    ax.plot(close.index, candle.ind.sma(30), color=AMBER, lw=1.0, label="SMA 30")
    tr = res.trades
    if not tr.empty:
        buys, sells = tr[tr.action == "BUY"], tr[tr.action == "SELL"]
        ax.scatter(buys.time, buys.price, marker="^", s=90, color=GREEN,
                   edgecolor=BG, zorder=5, label="BUY")
        ax.scatter(sells.time, sells.price, marker="v", s=90, color=RED,
                   edgecolor=BG, zorder=5, label="SELL")
    ax.set_title("yq backtest BTCUSDT 1d macross  —  signals on price")
    ax.legend(loc="upper left", ncol=4)
    _save(fig, "signals.png")


def chart_equity(candle: Candle) -> None:
    """Strategy equity curve vs buy-and-hold."""
    res = Backtest(candle, MACross(10, 30), cash=10_000, fee=0.001).run()
    eq = res.equity_curve["equity"]
    close = pd.Series(candle.close, index=candle.index)
    hold = 10_000 * close / close.iloc[0]
    fig, ax = plt.subplots(figsize=(10, 4.2))
    ax.plot(eq.index, eq, color=GREEN, lw=1.6, label="macross strategy")
    ax.plot(hold.index, hold, color=FG, lw=1.1, ls="--", alpha=0.7, label="buy & hold")
    s = res.stats
    ax.set_title(
        f"Equity curve  —  Sharpe {s.get('sharpe')}, "
        f"max DD {s.get('max_drawdown')}, trades {s.get('num_trades')}")
    ax.legend(loc="upper left")
    _save(fig, "equity.png")


def chart_indicators(candle: Candle) -> None:
    """Three-panel indicator view: price+Bollinger, RSI, MACD."""
    close = pd.Series(candle.close, index=candle.index)
    bb = candle.ind.bbands(20)
    rsi = candle.ind.rsi(14)
    macd = candle.ind.macd()
    fig, (a1, a2, a3) = plt.subplots(
        3, 1, figsize=(10, 7), sharex=True, gridspec_kw={"height_ratios": [3, 1, 1]})
    a1.plot(close.index, close, color=FG, lw=1.2, label="close")
    a1.plot(close.index, bb["upper"], color=ACCENT, lw=0.8, alpha=0.8)
    a1.plot(close.index, bb["lower"], color=ACCENT, lw=0.8, alpha=0.8)
    a1.fill_between(close.index, bb["lower"], bb["upper"], color=ACCENT, alpha=0.08)
    a1.set_title("candle.ind — Bollinger Bands · RSI · MACD")
    a1.legend(loc="upper left")
    a2.plot(rsi.index, rsi, color=AMBER, lw=1.0)
    a2.axhline(70, color=RED, lw=0.7, ls="--")
    a2.axhline(30, color=GREEN, lw=0.7, ls="--")
    a2.set_ylabel("RSI")
    a3.plot(macd.index, macd["macd"], color=ACCENT, lw=1.0, label="macd")
    a3.plot(macd.index, macd["signal"], color=AMBER, lw=1.0, label="signal")
    a3.bar(macd.index, macd["hist"], color=GRID, width=1.0)
    a3.set_ylabel("MACD")
    a3.legend(loc="upper left", ncol=2)
    _save(fig, "indicators.png")


def chart_ensemble(candle: Candle) -> None:
    """Equity curves of members vs a weighted ensemble blend."""
    members = {
        "macross": MACross(10, 30),
        "supertrend": SuperTrendFollow(10, 3.0),
        "rsi_reversion": RSIReversion(14),
    }
    fig, ax = plt.subplots(figsize=(10, 4.4))
    for (name, strat), col in zip(members.items(), (ACCENT, AMBER, "#a371f7")):
        eq = Backtest(candle, strat, cash=10_000, fee=0.001).run().equity_curve["equity"]
        ax.plot(eq.index, eq, lw=1.0, alpha=0.8, color=col, label=name)
    blend = Ensemble(list(members.values()), rule="weighted", threshold=0.4)
    eq = Backtest(candle, blend, cash=10_000, fee=0.001).run().equity_curve["equity"]
    ax.plot(eq.index, eq, lw=2.2, color=GREEN, label="weighted ensemble")
    ax.set_title("yq ensemble — members vs blended equity")
    ax.legend(loc="upper left", ncol=2)
    _save(fig, "ensemble.png")


def chart_drawdown(candle: Candle) -> None:
    """Underwater (drawdown) chart — equity below its running peak."""
    res = Backtest(candle, MACross(10, 30), cash=10_000, fee=0.001).run()
    eq = res.equity_curve["equity"]
    dd = (eq / eq.cummax() - 1.0) * 100.0
    fig, ax = plt.subplots(figsize=(10, 3.4))
    ax.fill_between(dd.index, dd, 0, color=RED, alpha=0.25)
    ax.plot(dd.index, dd, color=RED, lw=1.1)
    ax.set_ylabel("% below peak")
    ax.set_title(f"Underwater drawdown — trough {round(float(dd.min()), 2)}%")
    _save(fig, "drawdown.png")


def chart_monthly(candle: Candle) -> None:
    """Calendar heatmap of month-by-month returns."""
    from yammyquant.ops.operator import monthly_returns

    res = Backtest(candle, MACross(10, 30), cash=10_000, fee=0.001).run()
    mo = monthly_returns(res.equity_curve["equity"])
    z = np.array([[np.nan if v is None else v * 100 for v in row] for row in mo["matrix"]])
    months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
              "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    fig, ax = plt.subplots(figsize=(10, 1.4 + 0.5 * len(mo["years"])))
    vmax = np.nanmax(np.abs(z)) or 1.0
    im = ax.imshow(z, cmap="RdYlGn", vmin=-vmax, vmax=vmax, aspect="auto")
    ax.set_xticks(range(12), months)
    ax.set_yticks(range(len(mo["years"])), [str(y) for y in mo["years"]])
    for i in range(z.shape[0]):
        for j in range(z.shape[1]):
            if not np.isnan(z[i, j]):
                ax.text(j, i, f"{z[i, j]:.1f}", ha="center", va="center",
                        color=BG, fontsize=8)
    ax.set_title("Monthly returns (%)")
    fig.colorbar(im, ax=ax, fraction=0.025, pad=0.02)
    ax.grid(False)
    _save(fig, "monthly.png")


def chart_leaderboard(candle: Candle) -> None:
    """Strategy leaderboard — Sharpe ranking across strategies on one symbol."""
    from yammyquant.ops.operator import build_strategy

    names = ["keltner_breakout", "donchian_breakout", "bollinger_breakout",
             "macross", "ema_cross", "supertrend", "rsi_reversion", "macd_momentum"]
    rows = []
    for n in names:
        s = Backtest(candle, build_strategy(n), cash=10_000, fee=0.001).run().stats
        rows.append((n, s.get("sharpe") or 0.0))
    rows.sort(key=lambda r: r[1])
    fig, ax = plt.subplots(figsize=(10, 4.4))
    colors = [GREEN if v >= 0 else RED for _, v in rows]
    ax.barh([n for n, _ in rows], [v for _, v in rows], color=colors)
    ax.set_xlabel("sharpe")
    ax.set_title("yq compare — strategy leaderboard (by Sharpe)")
    ax.grid(axis="y", alpha=0)
    _save(fig, "leaderboard.png")


def chart_sensitivity(_candle: Candle) -> None:
    """Parameter-sensitivity heatmap — Sharpe across a fast × slow grid."""
    from yammyquant.backtest.optimize import grid_search

    candle = make_candle(n=600, seed=5)
    fast, slow = [5, 10, 15, 20, 30], [40, 60, 80, 100]
    res = grid_search(candle, MACross, {"fast": fast, "slow": slow}, metric="sharpe")
    lut = {(r["params"]["fast"], r["params"]["slow"]): r["score"] for r in res.results}
    z = np.array([[lut.get((f, s), np.nan) for f in fast] for s in slow])
    fig, ax = plt.subplots(figsize=(8, 4.2))
    im = ax.imshow(z, cmap="viridis", aspect="auto", origin="lower")
    ax.set_xticks(range(len(fast)), [str(f) for f in fast])
    ax.set_yticks(range(len(slow)), [str(s) for s in slow])
    ax.set_xlabel("fast")
    ax.set_ylabel("slow")
    for i in range(z.shape[0]):
        for j in range(z.shape[1]):
            if not np.isnan(z[i, j]):
                ax.text(j, i, f"{z[i, j]:.2f}", ha="center", va="center",
                        color="w", fontsize=8)
    ax.set_title("yq optimize — Sharpe sensitivity (fast × slow)")
    fig.colorbar(im, ax=ax, fraction=0.046, pad=0.02)
    ax.grid(False)
    _save(fig, "sensitivity.png")


def chart_correlation(_candle: Candle) -> None:
    """Return-correlation heatmap across a few synthetic symbols."""
    seeds = {"BTCUSDT": 7, "ETHUSDT": 11, "SOLUSDT": 21, "BNBUSDT": 3}
    rets = {s: pd.Series(make_candle(seed=sd).close).pct_change() for s, sd in seeds.items()}
    corr = pd.DataFrame(rets).dropna().corr()
    syms = list(corr.columns)
    z = corr.to_numpy()
    fig, ax = plt.subplots(figsize=(5.6, 5))
    im = ax.imshow(z, cmap="RdYlGn", vmin=-1, vmax=1)
    ax.set_xticks(range(len(syms)), syms, rotation=45, ha="right")
    ax.set_yticks(range(len(syms)), syms)
    for i in range(len(syms)):
        for j in range(len(syms)):
            ax.text(j, i, f"{z[i, j]:.2f}", ha="center", va="center", color=BG, fontsize=9)
    ax.set_title("yq correlate — return correlation")
    fig.colorbar(im, ax=ax, fraction=0.046, pad=0.02)
    ax.grid(False)
    _save(fig, "correlation.png")


def chart_walkforward(_candle: Candle) -> None:
    """Per-fold in-sample vs out-of-sample score — the overfitting gap.

    Uses a longer series so each train fold has enough bars for the grid's
    slowest MA (otherwise folds score 0 and the demo looks empty).
    """
    from yammyquant.backtest.optimize import walk_forward

    candle = make_candle(n=900, seed=11)
    wf = walk_forward(candle, MACross, {"fast": [5, 10, 20], "slow": [30, 50]},
                      n_splits=4, metric="sharpe")
    folds = wf["folds"]
    x = np.arange(len(folds))
    is_ = [f["in_sample_score"] for f in folds]
    oos = [f["out_of_sample"].get("sharpe", 0.0) for f in folds]
    fig, ax = plt.subplots(figsize=(10, 4.2))
    ax.bar(x - 0.2, is_, 0.4, color=ACCENT, label="in-sample")
    ax.bar(x + 0.2, oos, 0.4, color=GREEN, label="out-of-sample")
    ax.axhline(0, color=GRID, lw=0.8)
    ax.set_xticks(x)
    ax.set_xticklabels([f"fold {f['fold']}" for f in folds])
    ax.set_ylabel("sharpe")
    ax.set_title(f"walk-forward — avg OOS sharpe {wf['avg_out_of_sample']}")
    ax.legend(loc="upper left")
    _save(fig, "walkforward.png")


def main() -> None:
    candle = make_candle()
    chart_signals(candle)
    chart_equity(candle)
    chart_indicators(candle)
    chart_ensemble(candle)
    chart_drawdown(candle)
    chart_monthly(candle)
    chart_leaderboard(candle)
    chart_sensitivity(candle)
    chart_correlation(candle)
    chart_walkforward(candle)


if __name__ == "__main__":
    main()
