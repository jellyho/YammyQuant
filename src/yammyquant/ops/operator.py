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
