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


def main() -> None:
    candle = make_candle()
    chart_signals(candle)
    chart_equity(candle)
    chart_indicators(candle)
    chart_ensemble(candle)


if __name__ == "__main__":
    main()
