"""High-level operator actions — the toolbelt Claude Code drives.

Each function performs a unit of work against the 0.2 library (data store,
backtest engine, strategies) and records what it did to :class:`LiveState` so
the cockpit reflects it live. These are deliberately plain functions so they're
trivial to call from the CLI, a notebook, or directly in a Claude Code session.
"""

from __future__ import annotations

from typing import Optional

from yammyquant.data.sources.store import DuckDBStore
from yammyquant.backtest.engine import Backtest
from yammyquant.strategy.builtin import (
    MACross,
    VolatilityBreakout,
    RSIReversion,
    DonchianBreakout,
)
from yammyquant.state.store import LiveState

STRATEGIES = {
    "macross": MACross,
    "volatility_breakout": VolatilityBreakout,
    "rsi_reversion": RSIReversion,
    "donchian_breakout": DonchianBreakout,
}


def enabled_strategies(state: LiveState) -> list[str]:
    """Strategy names the user has enabled in the cockpit (default: all)."""
    settings = state.settings()
    return [
        name for name in STRATEGIES
        if settings.get(f"strategy.{name}.enabled", True)
    ]


# Default parameter grids used by `yq optimize` / `yq walkforward`.
DEFAULT_GRIDS = {
    "macross": {"fast": [5, 10, 20], "slow": [30, 50, 100]},
    "volatility_breakout": {"k": [0.3, 0.5, 0.7, 0.9]},
    "rsi_reversion": {"period": [7, 14, 21], "oversold": [20, 30], "overbought": [70, 80]},
    "donchian_breakout": {"period": [10, 20, 55]},
}


def optimize(
    store: DuckDBStore,
    ticker: str,
    interval: str,
    strategy: str,
    metric: str = "sharpe",
    grid: Optional[dict] = None,
    walk_forward_splits: int = 0,
    cash: float = 10_000.0,
    fee: float = 0.001,
    state: Optional[LiveState] = None,
) -> dict:
    """Grid-search a strategy's parameters (optionally walk-forward validated)."""
    from yammyquant.backtest.optimize import grid_search, walk_forward

    if strategy not in STRATEGIES:
        raise ValueError(f"unknown strategy {strategy!r}")
    candle = store.read(ticker, interval)
    grid = grid or DEFAULT_GRIDS.get(strategy, {})
    cls = STRATEGIES[strategy]

    if walk_forward_splits > 0:
        out = walk_forward(candle, cls, grid, n_splits=walk_forward_splits,
                           metric=metric, cash=cash, fee=fee)
        if state:
            state.log("optimize", f"walk-forward {strategy} on {ticker}/{interval}",
                      avg_out_of_sample=out["avg_out_of_sample"], metric=metric)
        return out

    res = grid_search(candle, cls, grid, metric=metric, cash=cash, fee=fee)
    out = {"metric": metric, "best_params": res.best_params,
           "best_score": round(res.best_score, 4),
           "top": [{"params": r["params"], "score": round(r["score"], 4)}
                   for r in res.results[:5]]}
    if state:
        state.log("optimize", f"optimized {strategy} on {ticker}/{interval}",
                  best_params=res.best_params, best_score=out["best_score"], metric=metric)
    return out


def build_strategy(name: str, **params):
    if name not in STRATEGIES:
        raise ValueError(f"unknown strategy {name!r}; choose from {sorted(STRATEGIES)}")
    return STRATEGIES[name](**params)


def collect(
    store: DuckDBStore,
    ticker: str,
    intervals: list[str],
    state: Optional[LiveState] = None,
) -> dict:
    """Backfill candles from Binance into the local store."""
    from yammyquant.data.sources.binance import backfill

    backfill(store, ticker, intervals)
    result = {iv: len(store.read(ticker, iv, start="1970-01-01 00:00:00")) for iv in intervals}
    if state:
        state.log("collect", f"collected {ticker} {intervals}", **result)
    return result


def backtest(
    store: DuckDBStore,
    ticker: str,
    interval: str,
    strategy: str,
    params: Optional[dict] = None,
    cash: float = 10_000.0,
    fee: float = 0.001,
    start: Optional[str] = None,
    end: Optional[str] = None,
    state: Optional[LiveState] = None,
) -> dict:
    """Run a backtest and return its headline stats."""
    candle = store.read(ticker, interval, start=start, end=end)
    strat = build_strategy(strategy, **(params or {}))
    result = Backtest(candle, strat, cash=cash, fee=fee).run()
    if state:
        state.log("backtest", f"backtest {strategy} on {ticker}/{interval}", **result.stats)
    return result.stats


def features(
    store: DuckDBStore,
    ticker: str,
    interval: str,
    feature_store=None,
    state: Optional[LiveState] = None,
) -> dict:
    """Compute candle-derived features, persist them, return the latest row."""
    from yammyquant.data.features import compute_features, latest_features, FeatureStore

    candle = store.read(ticker, interval)
    feats = compute_features(candle)
    fs = feature_store or FeatureStore()
    fs.write(ticker, interval, feats)
    latest = latest_features(candle)
    if state:
        state.log("features", f"computed {len(feats.columns)} features for {ticker}/{interval}",
                  latest=latest)
    return latest


def scan(
    store: DuckDBStore,
    tickers: list[str],
    interval: str,
    strategy: str,
    params: Optional[dict] = None,
    state: Optional[LiveState] = None,
) -> list[dict]:
    """Evaluate a strategy on the latest bar of each ticker and emit signals."""
    strat = build_strategy(strategy, **(params or {}))
    out = []
    for ticker in tickers:
        candle = store.read(ticker, interval)
        if len(candle) < strat.warmup:
            continue
        window = candle[-strat.warmup:]
        orders = strat.on_bar(window)
        action = orders[0].action.value if orders else "HOLD"
        row = {"ticker": ticker, "action": action, "price": float(candle.close[-1])}
        out.append(row)
        if state:
            state.add_signal(ticker, strategy, action, price=row["price"])
    if state:
        state.log("scan", f"scanned {len(tickers)} tickers with {strategy}",
                  signals=[r for r in out if r["action"] != "HOLD"])
    return out
