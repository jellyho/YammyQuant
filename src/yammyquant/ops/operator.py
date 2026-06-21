"""High-level operator actions — the toolbelt Claude Code drives.

Each function performs a unit of work against the 0.2 library (data store,
backtest engine, strategies) and records what it did to :class:`LiveState` so
the cockpit reflects it live. These are deliberately plain functions so they're
trivial to call from the CLI, a notebook, or directly in a Claude Code session.
"""

from __future__ import annotations

from typing import Optional, Sequence

from yammyquant.data.sources.store import DuckDBStore
from yammyquant.backtest.engine import Backtest
from yammyquant.strategy.builtin import (
    MACross,
    VolatilityBreakout,
    RSIReversion,
    DonchianBreakout,
    EMACross,
    TripleEMATrend,
    MACDMomentum,
    SuperTrendFollow,
    ADXTrend,
    ParabolicSARFlip,
    BollingerBreakout,
    KeltnerBreakout,
    BollingerReversion,
    StochasticScalp,
    StochRSIScalp,
    WilliamsRScalp,
    CCIReversion,
    MFIReversion,
    VWAPReversion,
)
from yammyquant.state.store import LiveState

STRATEGIES = {
    # trend following
    "macross": MACross,
    "ema_cross": EMACross,
    "triple_ema": TripleEMATrend,
    "macd_momentum": MACDMomentum,
    "supertrend": SuperTrendFollow,
    "adx_trend": ADXTrend,
    "parabolic_sar": ParabolicSARFlip,
    # breakout / volatility
    "volatility_breakout": VolatilityBreakout,
    "donchian_breakout": DonchianBreakout,
    "bollinger_breakout": BollingerBreakout,
    "keltner_breakout": KeltnerBreakout,
    # mean reversion / scalping
    "rsi_reversion": RSIReversion,
    "bollinger_reversion": BollingerReversion,
    "stochastic_scalp": StochasticScalp,
    "stoch_rsi_scalp": StochRSIScalp,
    "williams_r_scalp": WilliamsRScalp,
    "cci_reversion": CCIReversion,
    "mfi_reversion": MFIReversion,
    "vwap_reversion": VWAPReversion,
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
    "ema_cross": {"fast": [5, 9, 12], "slow": [21, 26, 50]},
    "triple_ema": {"fast": [5, 9], "mid": [21, 34], "slow": [55, 89]},
    "macd_momentum": {"fast": [8, 12], "slow": [21, 26], "signal": [9]},
    "supertrend": {"period": [7, 10, 14], "mult": [2.0, 3.0]},
    "adx_trend": {"period": [14], "threshold": [20.0, 25.0, 30.0]},
    "parabolic_sar": {"step": [0.02, 0.03], "max_step": [0.2]},
    "volatility_breakout": {"k": [0.3, 0.5, 0.7, 0.9]},
    "donchian_breakout": {"period": [10, 20, 55]},
    "bollinger_breakout": {"period": [14, 20], "std": [2.0, 2.5]},
    "keltner_breakout": {"period": [14, 20], "mult": [1.5, 2.0]},
    "rsi_reversion": {"period": [7, 14, 21], "oversold": [20, 30], "overbought": [70, 80]},
    "bollinger_reversion": {"period": [14, 20], "std": [2.0, 2.5]},
    "stochastic_scalp": {"k": [9, 14], "d": [3], "oversold": [20.0], "overbought": [80.0]},
    "stoch_rsi_scalp": {"period": [14], "k": [3], "d": [3]},
    "williams_r_scalp": {"period": [9, 14], "oversold": [-80.0], "overbought": [-20.0]},
    "cci_reversion": {"period": [14, 20], "threshold": [100.0, 150.0]},
    "mfi_reversion": {"period": [14], "oversold": [20.0], "overbought": [80.0]},
    "vwap_reversion": {"period": [14, 20], "threshold": [0.005, 0.01, 0.02]},
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
                   for r in res.results[:5]],
           # full grid (every param combo) for a sensitivity heatmap
           "results": [{"params": r["params"], "score": round(r["score"], 4)}
                       for r in res.results]}
    if state:
        state.log("optimize", f"optimized {strategy} on {ticker}/{interval}",
                  best_params=res.best_params, best_score=out["best_score"], metric=metric)
    return out


def build_strategy(name: str, **params):
    if name not in STRATEGIES:
        raise ValueError(f"unknown strategy {name!r}; choose from {sorted(STRATEGIES)}")
    return STRATEGIES[name](**params)


def build_ensemble(members: list[str], weights: Optional[list[float]] = None,
                   rule: str = "weighted", threshold: float = 0.5):
    """Build an :class:`Ensemble` from a list of strategy names."""
    from yammyquant.strategy.ensemble import Ensemble

    return Ensemble([build_strategy(m) for m in members],
                    weights=weights, rule=rule, threshold=threshold)


def ensemble_backtest(
    store: DuckDBStore,
    ticker: str,
    interval: str,
    members: list[str],
    weights: Optional[list[float]] = None,
    rule: str = "weighted",
    threshold: float = 0.5,
    cash: float = 10_000.0,
    fee: float = 0.001,
    state: Optional[LiveState] = None,
) -> dict:
    """Backtest a blend of strategies combined by a voting rule."""
    candle = store.read(ticker, interval)
    strat = build_ensemble(members, weights=weights, rule=rule, threshold=threshold)
    result = Backtest(candle, strat, cash=cash, fee=fee).run()
    stats = dict(result.stats)
    stats["members"] = members
    stats["rule"] = rule
    if state:
        state.log("ensemble", f"ensemble[{rule}] {members} on {ticker}/{interval}",
                  **result.stats)
    return stats


def collect(
    store: DuckDBStore,
    ticker: str,
    intervals: list[str],
    state: Optional[LiveState] = None,
    exchange: str = "binance",
    count: int = 200,
) -> dict:
    """Backfill candles into the local store from any supported exchange.

    ``exchange="binance"`` uses the resumable Binance backfill; any other name
    (``upbit``, ``bithumb``, ``kis``, or a ccxt id) uses that venue's adapter.
    """
    result = {}
    if exchange == "binance":
        from yammyquant.data.sources.binance import backfill

        backfill(store, ticker, intervals)
        result = {iv: len(store.read(ticker, iv, start="1970-01-01 00:00:00")) for iv in intervals}
    else:
        from yammyquant.exchanges import get_exchange

        adapter = get_exchange(exchange)
        for iv in intervals:
            candle = adapter.read(ticker, iv, count=count)
            if len(candle):
                store.write(candle)
            result[iv] = len(candle)
    if state:
        state.log("collect", f"collected {ticker} {intervals} from {exchange}", **result)
    return result


def buy_hold_benchmark(candle, index, start_equity: float):
    """Buy-and-hold equity over ``index``, anchored to ``start_equity``.

    Returns ``(series, total_return)`` — holding the asset across the same
    window the strategy traded, so its return is an apples-to-apples bar to
    clear. ``total_return`` is None when there's no usable price.
    """
    import pandas as pd
    close = pd.Series(candle.close, index=candle.index, dtype=float)
    bh = close.reindex(index).ffill()
    if len(bh) == 0 or not bh.iloc[0] or not start_equity:
        return bh * 0.0, None
    series = (bh / bh.iloc[0]) * start_equity
    return series, round(float(series.iloc[-1] / start_equity - 1.0), 4)


def backtest(
    store: DuckDBStore,
    ticker: str,
    interval: str,
    strategy: str,
    params: Optional[dict] = None,
    cash: float = 10_000.0,
    fee: float = 0.001,
    slippage: float = 0.0,
    fill_timing: str = "next_open",
    allow_short: bool = False,
    risk: Optional[dict] = None,
    bootstrap: int = 0,
    regime: Optional[dict] = None,
    start: Optional[str] = None,
    end: Optional[str] = None,
    state: Optional[LiveState] = None,
) -> dict:
    """Run a backtest and return its headline stats (+ buy-and-hold benchmark).

    ``risk`` is an optional dict of :class:`RiskConfig` fields (sizing,
    stop_loss, take_profit, trailing_stop, breakeven_trigger, max_holding_bars,
    max_drawdown, ...) wiring the protective-exit / position-sizing layer.
    ``bootstrap`` > 0 adds a bootstrapped Sharpe CI/p-value and the Probabilistic
    Sharpe Ratio — "is this edge statistically real, or noise?".
    ``regime`` (``{"trend_period": ..., "htf_factor": ...}``) wraps the strategy
    in a :class:`RegimeFilter` so it only enters with the prevailing trend.
    """
    candle = store.read(ticker, interval, start=start, end=end)
    strat = build_strategy(strategy, **(params or {}))
    if regime:
        from yammyquant.strategy.meta import RegimeFilter
        strat = RegimeFilter(strat, **{k: v for k, v in regime.items() if v is not None})
    risk_cfg = None
    if risk:
        from yammyquant.backtest.risk import RiskConfig
        risk_cfg = RiskConfig(**{k: v for k, v in risk.items() if v is not None})
    result = Backtest(candle, strat, cash=cash, fee=fee, slippage=slippage,
                      fill_timing=fill_timing, allow_short=allow_short,
                      risk=risk_cfg).run()
    stats = dict(result.stats)
    eq = result.equity_curve
    if len(eq):
        _, bench = buy_hold_benchmark(candle, eq.index, float(eq["equity"].iloc[0]))
        stats["benchmark_return"] = bench
        tr = stats.get("total_return")
        stats["excess_return"] = (round(tr - bench, 4)
                                  if bench is not None and tr is not None else None)
    if bootstrap and len(eq) > 2:
        from yammyquant.metrics.performance import (
            bootstrap_sharpe_ci, probabilistic_sharpe_ratio, _BARS_PER_YEAR)
        rets = eq["equity"].pct_change().dropna()
        ppy = _BARS_PER_YEAR.get(interval or "", 252)
        stats.update(bootstrap_sharpe_ci(rets, ppy, n_boot=int(bootstrap)))
        stats["psr"] = probabilistic_sharpe_ratio(rets)
    if state:
        state.log("backtest", f"backtest {strategy} on {ticker}/{interval}", **stats)
    return stats


def cost_sensitivity(
    store: DuckDBStore,
    ticker: str,
    interval: str,
    strategy: str,
    params: Optional[dict] = None,
    slippages: Optional[list] = None,
    fee: float = 0.001,
    cash: float = 10_000.0,
    fill_timing: str = "next_open",
    allow_short: bool = False,
    state: Optional[LiveState] = None,
) -> dict:
    """Sweep slippage to see how fast the edge erodes under trading costs.

    Re-runs the backtest at each slippage level and reports total return / Sharpe
    / drawdown / trades, plus ``breakeven_slippage`` — the first level where total
    return goes non-positive. A robust edge degrades gracefully; an overfit one
    collapses at the first whiff of cost.
    """
    grid = slippages if slippages is not None else [0.0, 0.0005, 0.001, 0.002, 0.005]
    rows = []
    for s in grid:
        r = backtest(store, ticker, interval, strategy, params, cash=cash, fee=fee,
                     slippage=float(s), fill_timing=fill_timing, allow_short=allow_short)
        rows.append({"slippage": float(s), "total_return": r.get("total_return"),
                     "sharpe": r.get("sharpe"), "max_drawdown": r.get("max_drawdown"),
                     "num_trades": r.get("num_trades")})
    breakeven = next((row["slippage"] for row in rows
                      if (row["total_return"] or 0) <= 0), None)
    if state:
        state.log("cost_sensitivity", f"cost sweep {strategy} on {ticker}/{interval}",
                  breakeven_slippage=breakeven)
    return {"strategy": strategy, "fee": fee, "rows": rows,
            "breakeven_slippage": breakeven}


def monthly_returns(equity) -> dict:
    """Calendar month-by-month returns from an equity series.

    Returns ``{"years": [...], "matrix": [[ret|None x12], ...]}`` where each row
    is a year and each column a month (Jan..Dec); cells with no data are None.
    Reveals consistency/seasonality at a glance (a heatmap in the dashboard).
    """
    import pandas as pd
    s = pd.Series(getattr(equity, "values", equity), dtype=float)
    s.index = pd.to_datetime(getattr(equity, "index", s.index))
    if len(s) < 2:
        return {"years": [], "matrix": []}
    monthly = s.resample("ME").last().pct_change().dropna()
    years = sorted({ts.year for ts in monthly.index})
    matrix = [[None] * 12 for _ in years]
    yi = {y: i for i, y in enumerate(years)}
    for ts, val in monthly.items():
        matrix[yi[ts.year]][ts.month - 1] = round(float(val), 4)
    return {"years": years, "matrix": matrix}


# headline columns surfaced by the strategy leaderboard
_COMPARE_FIELDS = ("total_return", "excess_return", "sharpe", "sortino",
                   "max_drawdown", "win_rate", "num_trades")


def compare(
    store: DuckDBStore,
    ticker: str,
    interval: str,
    strategies: Optional[Sequence[str]] = None,
    metric: str = "sharpe",
    cash: float = 10_000.0,
    fee: float = 0.001,
    optimize_each: bool = False,
    state: Optional[LiveState] = None,
) -> dict:
    """Backtest many strategies on one symbol and rank them by ``metric``.

    With ``optimize_each=False`` (default) each strategy runs at its default
    parameters; with ``optimize_each=True`` each is grid-searched first and
    ranked at its best params (a fair, tuned comparison) — the chosen params
    land in each row's ``params``. Rows carry the headline stats plus
    ``excess_return`` vs buy-and-hold. Strategies that error (e.g. too little
    data) are reported under ``errors`` rather than failing the run.
    """
    names = list(strategies) if strategies else list(STRATEGIES)
    unknown = [n for n in names if n not in STRATEGIES]
    if unknown:
        raise ValueError(f"unknown strategies: {unknown}")
    if metric not in _COMPARE_FIELDS and metric not in ("calmar", "cagr"):
        raise ValueError(f"unknown metric {metric!r}")

    # one stable buy-and-hold reference over the full loaded window, so it's
    # comparable across strategies regardless of their individual warmups.
    try:
        candle = store.read(ticker, interval)
        _, benchmark = buy_hold_benchmark(candle, candle.index, cash)
    except Exception:  # noqa: BLE001 - benchmark is informational, never fatal
        benchmark = None

    rows, errors = [], {}
    for name in names:
        try:
            params = None
            if optimize_each:
                # excess_return isn't an engine stat the grid can rank on; tune
                # on sharpe in that case, then report each strategy's excess.
                opt_metric = "sharpe" if metric == "excess_return" else metric
                opt = optimize(store, ticker, interval, name, metric=opt_metric,
                               cash=cash, fee=fee)
                params = opt.get("best_params") or {}
            stats = backtest(store, ticker, interval, name, params=params,
                             cash=cash, fee=fee)
        except Exception as e:  # noqa: BLE001 - surface per-strategy, keep going
            errors[name] = str(e)
            continue
        row = {"strategy": name,
               **{f: stats.get(f) for f in _COMPARE_FIELDS},
               "calmar": stats.get("calmar"), "cagr": stats.get("cagr")}
        if optimize_each:
            row["params"] = params
        rows.append(row)

    rows.sort(key=lambda r: (r.get(metric) is not None, r.get(metric) or 0.0), reverse=True)
    if state:
        best = rows[0]["strategy"] if rows else None
        state.log("compare", f"compared {len(rows)} strategies on {ticker}/{interval} by {metric}",
                  best=best, metric=metric)
    return {"ticker": ticker, "interval": interval, "metric": metric,
            "benchmark_return": benchmark, "ranking": rows, "errors": errors}


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


_INTERVAL_SECONDS = {
    "1m": 60, "3m": 180, "5m": 300, "10m": 600, "15m": 900, "30m": 1800,
    "1h": 3600, "2h": 7200, "4h": 14400, "6h": 21600, "12h": 43200,
    "1d": 86400, "1w": 604800, "1M": 2592000,
}


def mark(state: LiveState, exchange: Optional[str] = None, interval: str = "1m") -> dict:
    """Mark open positions to market using live prices, recording an equity point."""
    from yammyquant.exchanges import get_exchange, default_exchange
    from yammyquant.ops.trading import TradeManager

    ex = get_exchange(exchange or default_exchange())
    prices = {}
    for pos in state.positions():
        try:
            prices[pos["ticker"]] = ex.last_price(pos["ticker"], interval)
        except Exception as exc:  # keep going; report which failed
            state.log("mark", f"price fetch failed for {pos['ticker']}: {exc}")
    equity = TradeManager(state).mark_to_market(prices)
    state.log("mark", f"marked {len(prices)} positions; equity={equity:.2f}", equity=equity)
    return {"equity": equity, "prices": prices}


def integrity(store: DuckDBStore, ticker: Optional[str] = None,
              interval: Optional[str] = None) -> dict:
    """Audit stored candles for gaps, duplicates, bad OHLC and NaNs.

    With no ``ticker`` it scans every stored series; with a ``ticker`` (and
    optional ``interval``) it narrows the scan. Returns a per-series report and
    the list of series that flagged problems.
    """
    from yammyquant.data.integrity import candle_integrity

    targets = []
    for tk, intervals in store.info().items():
        if ticker and tk != ticker:
            continue
        for iv in intervals:
            if interval and iv != interval:
                continue
            targets.append((tk, iv))

    series, problems = [], []
    for tk, iv in targets:
        try:
            candle = store.read(tk, iv)
        except Exception as exc:
            series.append({"ticker": tk, "interval": iv, "error": str(exc), "ok": False})
            problems.append(f"{tk}/{iv}")
            continue
        rep = candle_integrity(candle, _INTERVAL_SECONDS.get(iv))
        rep.update(ticker=tk, interval=iv)
        series.append(rep)
        if not rep["ok"]:
            problems.append(f"{tk}/{iv}")
    return {"ok": not problems, "problems": problems, "series": series}


def doctor(store: DuckDBStore, state: LiveState, stale_factor: float = 3.0) -> dict:
    """Health check: data freshness, integrity, config completeness, account sanity."""
    from datetime import datetime, timezone
    from yammyquant.exchanges import describe

    now = datetime.now(timezone.utc)
    data = []
    for ticker, intervals in store.info().items():
        for iv in intervals:
            last = store.last_time(ticker, iv)
            age = (now - last.replace(tzinfo=timezone.utc)).total_seconds() if last else None
            limit = _INTERVAL_SECONDS.get(iv, 86400) * stale_factor
            data.append({"ticker": ticker, "interval": iv,
                         "last": str(last) if last else None,
                         "stale": age is None or age > limit})

    cfg = describe()
    configured = {n: all(v != "missing" for v in d["credentials"].values())
                  for n, d in cfg["exchanges"].items()}
    issues = [f"{d['ticker']}/{d['interval']} stale" for d in data if d["stale"]]
    if not state.get("cash"):
        issues.append("cash not initialized (set via a paper trade or config)")

    integ = integrity(store)
    issues += [f"{p} data integrity" for p in integ["problems"]]

    return {
        "ok": not issues,
        "issues": issues,
        "data_freshness": data,
        "data_integrity": integ["problems"],
        "exchanges_configured": configured,
        "default_exchange": cfg["default_exchange"],
        "pending_trades": len(state.trades(status="pending")),
        "open_positions": len(state.positions()),
    }


def run_cycle(store: DuckDBStore, state: LiveState, exchange: Optional[str] = None,
              count: int = 200, notify_signals: bool = True) -> dict:
    """
              Refreshes watchlist data, scans enabled strategies for signals, and marks equity to market.
              
              Fetches latest candles for each watchlist item, stores them, evaluates each enabled
              strategy, generates buy/sell signals, updates equity, and optionally sends notifications.
              If `auto_trade` is enabled, also executes trading decisions.
              
              Parameters:
              	exchange (str, optional): Exchange name (e.g., "binance"). If None, uses default.
              	count (int): Number of candles per read (default 200).
              	notify_signals (bool): Whether to send alert notifications for non-empty signals (default True).
              
              Returns:
              	dict: Contains "refreshed" (list of refreshed symbols), "signals" (list of signal dicts
              	with symbol/strategy/action), "equity" (current portfolio equity or None if no positions),
              	and "decisions" (auto-trade result dict if auto_trade is enabled, else None).
              """
    from yammyquant.exchanges import get_exchange, default_exchange
    from yammyquant.ops.notify import notify
    from yammyquant.ops.trading import TradeManager

    ex = get_exchange(exchange or default_exchange())
    enabled = enabled_strategies(state)
    refreshed, signals = [], []

    # pull any user instructions left in Slack/Discord into the inbox first
    inbound = None
    try:
        from yammyquant.feeds.inbound import collect_inbound, inbound_channels
        if inbound_channels():
            inbound = collect_inbound(state)
    except Exception as exc:
        state.log("inbound", f"cycle inbound poll failed: {exc}", level="warn")

    for w in state.watchlist():
        sym, iv = w["symbol"], (w["interval"] or "1d")
        try:
            candle = ex.read(sym, iv, count=count)
            store.write(candle)
            refreshed.append(sym)
        except Exception as exc:
            state.log("cycle", f"refresh failed for {sym}: {exc}")
            continue
        for name in enabled:
            strat = build_strategy(name)
            if len(candle) < strat.warmup:
                continue
            orders = strat.on_bar(candle[-strat.warmup:])
            if orders and orders[0].action.value != "HOLD":
                action = orders[0].action.value
                state.add_signal(sym, name, action, price=float(candle.close[-1]))
                signals.append({"symbol": sym, "strategy": name, "action": action})

    prices = {}
    for pos in state.positions():
        try:
            prices[pos["ticker"]] = ex.last_price(pos["ticker"])
        except Exception:
            pass
    equity = TradeManager(state).mark_to_market(prices) if state.positions() else None

    state.log("cycle", f"cycle: {len(refreshed)} refreshed, {len(signals)} signals",
              refreshed=refreshed, signals=signals)

    decisions = None
    if state.get("auto_trade"):  # opt-in autonomous trading
        decisions = decide(store, state, exchange=exchange,
                           mode=state.get("trade_mode", "paper"), execute=True)

    if notify_signals and signals:
        summary = ", ".join(f"{s['action']} {s['symbol']}({s['strategy']})" for s in signals[:5])
        notify(state, f"🔔 {len(signals)} signal(s): {summary}", "action")
    return {"refreshed": refreshed, "signals": signals, "equity": equity,
            "decisions": decisions, "inbound": inbound}


def collect_news(
    state: LiveState,
    sources: Optional[dict] = None,
    limit_per: int = 15,
    store_all: bool = False,
    notify_watch: bool = True,
) -> dict:
    """
    Collect news from RSS feeds, tag items to watchlist symbols, and score sentiment.
    
    Parameters:
        sources (dict, optional): Feed labels to URLs; if None, uses defaults merged with state configuration
    
    Returns:
        dict: Contains "stored" (total items added) and "tagged" (items tagged to watchlist)
    """
    from yammyquant.feeds.rss import RSSFeed, tag_symbols
    from yammyquant.feeds.sentiment import score_text
    from yammyquant.feeds.sources import DEFAULT_SOURCES, DEFAULT_KEYWORDS

    sources = sources or {**DEFAULT_SOURCES, **(state.get("news_sources") or {})}
    watched = {w["symbol"] for w in state.watchlist()}
    kw = {**DEFAULT_KEYWORDS, **(state.get("news_keywords") or {})}
    symbols = {s: kw.get(s, []) for s in watched}

    stored, tagged, alerts = 0, 0, []
    for label, url in sources.items():
        try:
            items = RSSFeed(url, label).fetch()
        except Exception as exc:
            state.log("news", f"feed {label} failed: {exc}")
            continue
        for it in items[:limit_per]:
            sym = tag_symbols(it, symbols) if symbols else None
            if sym is None and not store_all:
                continue
            it.symbol = sym or ""
            it.sentiment = score_text(f"{it.title} {it.summary}")
            if state.add_news(**it.as_record()):
                stored += 1
                if sym:
                    tagged += 1
                    alerts.append((sym, it.title))
    if notify_watch and alerts:
        from yammyquant.ops.notify import notify
        head = "; ".join(f"{s}: {t[:60]}" for s, t in alerts[:3])
        notify(state, f"📰 {len(alerts)} watchlist headline(s): {head}", "info")
    state.log("news", f"collected {stored} item(s), {tagged} tagged to watchlist")
    return {"stored": stored, "tagged": tagged}


def news_sentiment(state: LiveState, symbol: str, lookback: int = 20) -> dict:
    """
    Computes the average sentiment score of recent stored news for a symbol.
    
    Returns:
    	A dict with the symbol, count of retrieved news rows, and average sentiment rounded to three decimal places (0.0 if no sentiment values available).
    """
    rows = state.news(symbol=symbol, limit=lookback)
    scores = [r["sentiment"] for r in rows if r.get("sentiment") is not None]
    return {"symbol": symbol, "count": len(rows),
            "avg_sentiment": round(sum(scores) / len(scores), 3) if scores else 0.0}


def brief(store: DuckDBStore, state: LiveState, ticker: str, interval: str = "1d",
          exchange: Optional[str] = None) -> dict:
    """
          Assemble a one-screen research digest with price, features, news sentiment, and position.
          
          Parameters:
          	exchange (str, optional): Exchange name to fetch fundamentals from (for stock assets only).
          
          Returns:
          	digest (dict): Contains ticker, interval, price, bar count, features, news items with 
          		sentiment, average sentiment, current position (if held), and optional fundamentals. 
          		Includes data_error if candle read fails, fundamentals_error if fundamentals fetch fails.
          """
    from yammyquant.data.features import latest_features

    out = {"ticker": ticker, "interval": interval}
    try:
        candle = store.read(ticker, interval)
        out["price"] = float(candle.close[-1])
        out["bars"] = len(candle)
        out["features"] = latest_features(candle)
    except Exception as exc:
        out["data_error"] = str(exc)

    out["news"] = [{"title": n["title"], "sentiment": n["sentiment"],
                    "published": n["published"], "source": n["source"], "url": n["url"]}
                   for n in state.news(symbol=ticker, limit=8)]
    out["news_sentiment"] = news_sentiment(state, ticker)["avg_sentiment"]

    if exchange:
        try:
            from yammyquant.exchanges import get_exchange
            ex = get_exchange(exchange)
            if getattr(ex, "asset_class", "") == "stock" and hasattr(ex, "fundamentals"):
                out["fundamentals"] = ex.fundamentals(ticker)
        except Exception as exc:
            out["fundamentals_error"] = str(exc)

    out["position"] = {p["ticker"]: p for p in state.positions()}.get(ticker)
    state.log("brief", f"research brief for {ticker}")
    return out


def recall(state: LiveState, query: Optional[str] = None, limit: int = 5,
           half_life_days: float = 14.0) -> dict:
    """Memory-stream retrieval — what a fresh session should know right now.

    Ranks journal entries by ``recency × importance × relevance`` (the Generative-
    Agents memory pattern) and bundles unread inbox + open positions, so an
    ephemeral operator can reconstruct context in one call at session start.
    """
    import re
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    q_terms = set(re.findall(r"\w+", query.lower())) if query else set()

    def _score(entry: dict) -> tuple[float, float, float, float]:
        try:
            age_days = (now - datetime.fromisoformat(entry["ts"])).total_seconds() / 86400
        except Exception:
            age_days = 0.0
        recency = 0.5 ** (max(age_days, 0.0) / half_life_days)          # half-life decay
        imp = entry.get("importance")
        importance = (float(imp) / 10.0) if imp is not None else 0.5    # 1..10 → 0..1
        relevance = 0.0
        if q_terms:
            words = set(re.findall(r"\w+", f"{entry['text']} {entry.get('tag') or ''}".lower()))
            relevance = len(q_terms & words) / len(q_terms)
        return round(0.45 * recency + 0.35 * importance + 0.20 * relevance, 4), recency, importance, relevance

    ranked = []
    for e in state.journal(limit=200):
        sc, rec, imp, rel = _score(e)
        ranked.append({**e, "_score": sc, "_rel": rel})
    if q_terms:
        ranked = [r for r in ranked if r["_rel"] > 0] or ranked      # drop noise when querying
    ranked.sort(key=lambda r: r["_score"], reverse=True)
    top = ranked[:limit]
    state.bump_journal_recall([t["id"] for t in top])

    hints = {k: state.get(k) for k in ("auto_trade", "trade_mode", "sentiment_gate")
             if state.get(k) is not None}
    return {
        "query": query,
        "unread_inbox": state.inbox(only_unread=True),
        "memories": [{"id": t["id"], "ts": t["ts"], "tag": t["tag"], "text": t["text"],
                      "importance": t["importance"], "score": t["_score"]} for t in top],
        "open_positions": [{"ticker": p["ticker"], "quantity": p["quantity"],
                            "avg_price": p["avg_price"]} for p in state.positions()],
        "settings": hints,
    }


def decide(
    store: DuckDBStore,
    state: LiveState,
    exchange: Optional[str] = None,
    mode: str = "paper",
    weight: Optional[float] = None,
    count: int = 200,
    execute: bool = False,
    order_type: str = "market",
) -> dict:
    """Aggregate enabled-strategy signals into risk-sized trading proposals.
    
    For each watchlist symbol, enabled-strategy signals are combined into unified
    decisions: BUY (sized to ``weight`` of equity when flat) or SELL (closing entire
    position). BUY decisions may be gated by recent news sentiment if configured.
    With ``execute=True``, proposals are submitted to the exchange; otherwise
    returned for review.
    """
    from yammyquant.exchanges import get_exchange, default_exchange
    from yammyquant.ops.trading import TradeManager
    from yammyquant.ops.risk_policy import AccountRiskPolicy

    ex = get_exchange(exchange or default_exchange())
    tm = TradeManager(state)
    policy = AccountRiskPolicy.load(state)
    target_w = weight if weight is not None else (policy.max_symbol_weight or 0.1)
    equity = tm._equity_estimate()
    positions = {p["ticker"]: p for p in state.positions()}
    enabled = enabled_strategies(state)

    proposals = []
    for w in state.watchlist():
        sym, iv = w["symbol"], (w["interval"] or "1d")
        try:
            candle = ex.read(sym, iv, count=count)
        except Exception as exc:
            state.log("decide", f"read failed for {sym}: {exc}")
            continue
        actions = set()
        votes, vote_weights, voters = [], [], {}
        for name in enabled:
            strat = build_strategy(name)
            if len(candle) < strat.warmup:
                continue
            orders = strat.on_bar(candle[-strat.warmup:])
            vote = orders[0].action.value if orders else "HOLD"
            votes.append(vote)
            vote_weights.append(float(state.get(f"strategy.{name}.weight", 1.0)))
            voters[name] = vote
            if orders:
                actions.add(vote)

        from yammyquant.strategy.ensemble import aggregate_votes
        rule = state.get("ensemble_rule", "any")
        threshold = float(state.get("ensemble_threshold", 0.5))
        agg = aggregate_votes(votes, vote_weights, rule, threshold)

        price = float(candle.close[-1])
        held = sym in positions and positions[sym]["quantity"] > 0
        active = {n: v for n, v in voters.items() if v != "HOLD"}  # who actually fired
        context = {"voters": active or voters, "rule": rule, "score": agg["score"],
                   "equity": round(equity, 2)}
        decision = None
        if agg["sell"] and held:
            decision = {"symbol": sym, "side": "SELL", "quantity": positions[sym]["quantity"],
                        "price": price,
                        "reason": f"exit signal — {rule} vote score {agg['score']} "
                                  f"({sum(v == 'SELL' for v in votes)} of {len(votes)} sell)",
                        "context": context}
        elif agg["buy"] and not agg["sell"] and not held and price > 0:
            # optional sentiment gate: veto entries when recent news is strongly negative
            gate = state.get("sentiment_gate")
            senti = news_sentiment(state, sym)["avg_sentiment"] if gate is not None else 0.0
            if gate is not None and senti < float(gate):
                state.log("decide", f"vetoed BUY {sym}: sentiment {senti} < gate {gate}")
                continue
            qty = round((equity * target_w) / price, 8)
            if qty > 0:
                from yammyquant.ops.sizing import position_size
                method = state.get("sizing", "fixed")
                qty = position_size(method, equity, price, target_w, candle=candle,
                                    trades=state.trades(limit=200),
                                    target_vol=float(state.get("target_vol", 0.5)))
            if qty > 0:
                buyers = sum(v == "BUY" for v in votes)
                reason = (f"entry signal — {rule} vote score {agg['score']} "
                          f"({buyers} of {len(votes)} buy); {method} size "
                          f"{qty * price / equity:.1%} of equity (≈{qty * price:,.0f})")
                if gate is not None:
                    reason += f"; sentiment {senti}"
                    context["sentiment"] = senti
                context["weight"] = target_w
                context["sizing"] = method
                decision = {"symbol": sym, "side": "BUY", "quantity": qty, "price": price,
                            "reason": reason, "context": context}
        if decision is None:
            continue
        if execute:
            res = tm.submit(decision["symbol"], decision["side"], decision["quantity"],
                            decision["price"], mode=mode, rationale=decision["reason"],
                            order_type=order_type, context=decision["context"])
            decision["status"] = res["status"]
            decision["trade_id"] = res["id"]
        proposals.append(decision)

    state.log("decide", f"{len(proposals)} decision(s) (execute={execute}, mode={mode})",
              proposals=proposals)
    return {"execute": execute, "mode": mode, "weight": target_w, "proposals": proposals}


def rebalance(
    store: DuckDBStore,
    state: LiveState,
    targets: Optional[dict] = None,
    exchange: Optional[str] = None,
    mode: str = "paper",
    band: float = 0.02,
    execute: bool = False,
) -> dict:
    """Move the portfolio toward target weights (target-weight maintenance).

    ``targets`` maps symbol -> desired fraction of equity (defaults to the stored
    ``targets`` setting). Symbols whose weight drifts more than ``band`` from
    target get a buy/sell to close the gap; cash is the implicit remainder.
    """
    from yammyquant.exchanges import get_exchange, default_exchange
    from yammyquant.ops.trading import TradeManager

    targets = targets or state.get("targets", {})
    if not targets:
        return {"orders": [], "note": "no targets set (yq target set SYM=weight)"}

    ex = get_exchange(exchange or default_exchange())
    tm = TradeManager(state)
    positions = {p["ticker"]: p for p in state.positions()}
    prices = {}
    for sym in set(targets) | set(positions):
        try:
            prices[sym] = ex.last_price(sym)
        except Exception:
            prices[sym] = positions.get(sym, {}).get("avg_price", 0.0)

    equity = tm.cash + sum(positions[s]["quantity"] * prices.get(s, 0.0) for s in positions)
    orders = []
    for sym, target_w in targets.items():
        price = prices.get(sym, 0.0)
        if price <= 0:
            continue
        cur_val = positions.get(sym, {}).get("quantity", 0.0) * price
        cur_w = cur_val / equity if equity else 0.0
        if abs(cur_w - target_w) <= band:
            continue
        delta_val = target_w * equity - cur_val
        side = "BUY" if delta_val > 0 else "SELL"
        qty = round(abs(delta_val) / price, 8)
        if qty <= 0:
            continue
        order = {"symbol": sym, "side": side, "quantity": qty, "price": price,
                 "current_weight": round(cur_w, 4), "target_weight": target_w}
        if execute:
            res = tm.submit(sym, side, qty, price, mode=mode, rationale="rebalance")
            order["status"] = res["status"]
        orders.append(order)

    state.log("rebalance", f"{len(orders)} rebalancing order(s) (execute={execute})", orders=orders)
    return {"execute": execute, "mode": mode, "equity": round(equity, 2), "orders": orders}


def record_expectation(
    store: DuckDBStore,
    state: LiveState,
    ticker: str,
    interval: str,
    strategy: str,
    params: Optional[dict] = None,
    name: Optional[str] = None,
) -> dict:
    """Backtest a strategy and store its result as the live performance baseline."""
    stats = backtest(store, ticker, interval, strategy, params)
    key = name or f"{strategy}:{ticker}:{interval}"
    expectations = state.get("expectations", {})
    expectations[key] = {"sharpe": stats.get("sharpe"), "total_return": stats.get("total_return"),
                         "win_rate": stats.get("win_rate"), "max_drawdown": stats.get("max_drawdown"),
                         "recorded_at": __import__("datetime").datetime.utcnow().isoformat()}
    state.set("expectations", expectations)
    state.log("expect", f"recorded expectation {key}", **expectations[key])
    return {key: expectations[key]}


def decay_check(state: LiveState, tolerance: float = 0.5) -> dict:
    """Compare realized account performance to recorded backtest expectations.

    Flags a strategy as *decayed* when the live/paper Sharpe falls below
    ``tolerance`` × the backtested Sharpe — an early warning that an edge has
    stopped working out of sample. (Account-level: most meaningful when one
    strategy drives the book.)
    """
    expectations = state.get("expectations", {})
    realized = report(state)
    out = []
    for key, exp in expectations.items():
        exp_sharpe = exp.get("sharpe") or 0.0
        decayed = exp_sharpe > 0 and realized["sharpe"] < tolerance * exp_sharpe
        out.append({"expectation": key, "expected_sharpe": exp_sharpe,
                    "realized_sharpe": realized["sharpe"],
                    "expected_return": exp.get("total_return"),
                    "realized_return": realized["total_return"], "decayed": decayed})
    decayed_any = [o for o in out if o["decayed"]]
    if decayed_any:
        from yammyquant.ops.notify import notify
        notify(state, f"⚠️ strategy decay: {', '.join(o['expectation'] for o in decayed_any)}", "warn")
    return {"realized_sharpe": realized["sharpe"], "checks": out}


def report(state: LiveState, interval: Optional[str] = None) -> dict:
    """Performance report from recorded equity + trades (realized PnL, drawdown…)."""
    import pandas as pd
    from yammyquant.metrics.performance import (
        max_drawdown, sharpe, sortino, expectancy, _BARS_PER_YEAR,
    )

    eqrows = state.equity_curve()
    equity = pd.Series([r["equity"] for r in eqrows], dtype=float)
    rets = equity.pct_change().dropna() if len(equity) > 1 else pd.Series(dtype=float)
    ppy = _BARS_PER_YEAR.get(interval or "", 365)

    sells = [t for t in state.trades(limit=2000) if t["status"] == "filled" and t["side"] == "SELL"]
    realized, by_symbol = [], {}
    for t in sells:
        meta = t.get("meta")
        if isinstance(meta, dict) and "realized" in meta:
            r = float(meta["realized"])
            realized.append(r)
            by_symbol[t["ticker"]] = round(by_symbol.get(t["ticker"], 0.0) + r, 4)
    wins = [r for r in realized if r > 0]
    losses = [r for r in realized if r < 0]
    pnl = pd.Series(realized, dtype=float)

    out = {
        "equity_start": round(float(equity.iloc[0]), 2) if len(equity) else None,
        "equity_now": round(float(equity.iloc[-1]), 2) if len(equity) else None,
        "total_return": round(float(equity.iloc[-1] / equity.iloc[0] - 1), 4)
                        if len(equity) > 1 and equity.iloc[0] else 0.0,
        "max_drawdown": round(max_drawdown(equity), 4) if len(equity) else 0.0,
        "sharpe": round(sharpe(rets, ppy), 3),
        "sortino": round(sortino(rets, ppy), 3),
        "realized_pnl": round(sum(realized), 4),
        "closed_trades": len(realized),
        "win_rate": round(len(wins) / len(realized), 4) if realized else 0.0,
        "profit_factor": round(sum(wins) / abs(sum(losses)), 3) if losses else None,
        "expectancy": round(expectancy(pnl), 4) if realized else 0.0,
        "avg_win": round(sum(wins) / len(wins), 4) if wins else 0.0,
        "avg_loss": round(sum(losses) / len(losses), 4) if losses else 0.0,
        "realized_by_symbol": by_symbol,
        "open_positions": state.positions(),
        "cash": state.get("cash", 0.0),
    }
    state.log("report", "performance report", realized_pnl=out["realized_pnl"],
              total_return=out["total_return"])
    return out


def notify_status(state: LiveState) -> dict:
    """Build a compact status digest and push it to Discord/Slack."""
    from yammyquant.ops.notify import notify, channels

    rep = report(state)
    positions = state.positions()
    pending = state.trades(status="pending")
    parts = [
        f"equity {rep.get('equity_now')}",
        f"return {rep.get('total_return')}",
        f"realized PnL {rep.get('realized_pnl')}",
        f"positions {len(positions)}",
    ]
    if rep.get("closed_trades"):
        # edge health at a glance when there's a track record to summarize
        parts.append(f"win {rep['win_rate']} · exp {rep['expectancy']}")
    if pending:
        parts.append(f"⏳ {len(pending)} pending approval(s)")
    message = "📊 status — " + " · ".join(str(p) for p in parts)
    sent = notify(state, message, "info")
    return {"message": message, "sent": sent, "channels": channels()}


def listen(state: LiveState) -> dict:
    """Poll Slack/Discord for new user messages and post them to the inbox.

    The return path for operator control: instructions the user types in their
    chat channel land in the inbox and surface on the next ``yq recall``.
    """
    from yammyquant.feeds.inbound import collect_inbound, inbound_channels
    out = collect_inbound(state)
    out["channels"] = inbound_channels()
    return out


def portfolio_backtest(store: DuckDBStore, symbols, interval: str, strategy: str,
                       params: Optional[dict] = None, weights: Optional[list] = None,
                       cash: float = 10_000.0, fee: float = 0.001,
                       risk_parity: bool = False, diversified: bool = False) -> dict:
    """Backtest a strategy across several symbols and combine into one portfolio.

    Capital is split by ``weights`` (equal by default; inverse-volatility when
    ``risk_parity=True``; correlation-aware inverse-vol when ``diversified=True``);
    each symbol runs its own single-symbol backtest with its slice of cash, and
    the per-symbol equity curves are aligned and summed into a portfolio curve +
    headline stats.
    """
    import pandas as pd
    from yammyquant.metrics.performance import summary

    symbols = [s for s in symbols if s]
    if not symbols:
        raise ValueError("need at least one symbol")
    if weights is None and (diversified or risk_parity):
        wmap = (diversified_weights(store, symbols, interval) if diversified
                else risk_parity_weights(store, symbols, interval))
        symbols = list(wmap)
        weights = [wmap[s] for s in symbols]
    weights = weights or [1.0 / len(symbols)] * len(symbols)
    if len(weights) != len(symbols):
        raise ValueError("weights length must match symbols")
    total = sum(weights) or 1.0
    weights = [w / total for w in weights]

    per_symbol, curves = {}, []
    for sym, w in zip(symbols, weights):
        candle = store.read(sym, interval)
        res = Backtest(candle, build_strategy(strategy, **(params or {})),
                       cash=cash * w, fee=fee).run()
        per_symbol[sym] = {**res.stats, "weight": round(w, 4)}
        eq = res.equity_curve["equity"].copy()
        eq.name = sym
        curves.append(eq)

    combined = pd.concat(curves, axis=1).sort_index().ffill().bfill()
    portfolio = combined.sum(axis=1)
    stats = summary(pd.DataFrame({"equity": portfolio}), pd.DataFrame(), interval=interval)

    # weighted buy-and-hold benchmark: hold the basket (each leg w*cash) from
    # the start over the same index — the bar the active portfolio must clear.
    bench = pd.Series(0.0, index=portfolio.index)
    for sym, w in zip(symbols, weights):
        leg, _ = buy_hold_benchmark(store.read(sym, interval), portfolio.index, cash * w)
        bench = bench.add(leg, fill_value=0.0)
    bench_return = round(float(bench.iloc[-1] / cash - 1.0), 4) if len(bench) and cash else None
    bmap = {ts: float(v) for ts, v in bench.items()}

    points = [{"ts": str(ts), "equity": float(v), "bench": bmap.get(ts)}
              for ts, v in portfolio.items()]
    step = max(1, len(points) // 400)
    return {"symbols": symbols, "interval": interval, "strategy": strategy,
            "portfolio": stats, "per_symbol": per_symbol,
            "benchmark_return": bench_return, "equity": points[::step]}


def correlation(store: DuckDBStore, symbols, interval: str = "1d",
                lookback: int = 120) -> dict:
    """Return-correlation matrix across symbols — a diversification check.

    Aligns each symbol's daily returns on a common index and correlates the most
    recent ``lookback`` overlapping bars. Symbols without data are skipped.
    """
    import pandas as pd

    symbols = [s for s in symbols if s]
    if len(symbols) < 2:
        raise ValueError("need at least two symbols")
    cols = {}
    for sym in symbols:
        try:
            candle = store.read(sym, interval)
        except Exception:
            continue
        cols[sym] = pd.Series(candle.close, index=candle.index, dtype=float).pct_change()
    if len(cols) < 2:
        raise ValueError("need at least two symbols with data")
    df = pd.DataFrame(cols).dropna().tail(lookback)
    corr = df.corr()
    syms = list(corr.columns)
    matrix = [[round(float(corr.loc[a, b]), 3) for b in syms] for a in syms]
    return {"symbols": syms, "matrix": matrix, "lookback": lookback, "bars": len(df)}


def risk_parity_weights(store: DuckDBStore, symbols, interval: str = "1d",
                        lookback: int = 60) -> dict:
    """Inverse-volatility ('risk parity') target weights across symbols.

    Each symbol's weight is proportional to 1/realized-vol so every holding
    contributes roughly equal risk; weights are normalized to sum to 1. Symbols
    with no data (or zero vol) are skipped.
    """
    import pandas as pd

    symbols = [s for s in symbols if s]
    if not symbols:
        raise ValueError("need at least one symbol")
    inv_vol = {}
    for sym in symbols:
        try:
            candle = store.read(sym, interval)
        except Exception:
            continue
        rets = pd.Series(candle.close, dtype=float).pct_change().dropna()
        if len(rets) < 2:
            continue
        vol = float(rets.tail(lookback).std()) * (252 ** 0.5)
        if vol > 0:
            inv_vol[sym] = 1.0 / vol
    total = sum(inv_vol.values())
    if not total:
        raise ValueError("no symbols with usable volatility")
    return {sym: round(w / total, 4) for sym, w in inv_vol.items()}


def diversified_weights(store: DuckDBStore, symbols, interval: str = "1d",
                        lookback: int = 60) -> dict:
    """Correlation-aware weights: inverse-vol tilted toward diversifiers.

    Starts from inverse-volatility (risk parity) and multiplies each symbol's
    weight by a diversification factor ``1 - mean(correlation to the others)``,
    so assets that move with the rest of the book are downweighted and genuine
    diversifiers (low or negative correlation) are boosted. Falls back to
    inverse-vol when fewer than two symbols have overlapping data.
    """
    import numpy as np
    import pandas as pd

    symbols = [s for s in symbols if s]
    if not symbols:
        raise ValueError("need at least one symbol")
    series = {}
    for sym in symbols:
        try:
            candle = store.read(sym, interval)
        except Exception:
            continue
        r = pd.Series(candle.close, index=pd.DatetimeIndex(candle.index),
                      dtype=float).pct_change()
        if r.notna().sum() >= 2:
            series[sym] = r
    if not series:
        raise ValueError("no symbols with usable data")

    frame = pd.concat(series, axis=1).dropna().tail(lookback)
    if frame.shape[1] < 2 or len(frame) < 3:
        return risk_parity_weights(store, list(series), interval, lookback)

    vol = frame.std() * (252 ** 0.5)
    inv_vol = (1.0 / vol).replace([np.inf, -np.inf], np.nan).dropna()
    corr = frame.corr()
    n = corr.shape[1]
    avg_corr = (corr.sum(axis=1) - 1.0) / (n - 1)          # mean signed corr to others
    divers = (1.0 - avg_corr).clip(lower=0.05)             # downweight the crowd, boost diversifiers
    raw = (inv_vol * divers).dropna()
    total = float(raw.sum())
    if total <= 0:
        raise ValueError("no symbols with usable volatility")
    return {sym: round(float(w) / total, 4) for sym, w in raw.items()}


def attribution(state: LiveState) -> dict:
    """Per-strategy performance attribution from executed trades.

    `decide` enters/exits a symbol all-at-once, so each symbol is one open
    round-trip at a time: a closed SELL's realized PnL is credited to the
    strategies that voted to *enter* (the last BUY's voters). Approximate but
    honest — only trades carrying decision context are attributed.
    """
    trades = sorted(state.trades(limit=2000), key=lambda t: t["id"])
    entry_voters: dict[str, list] = {}
    by: dict[str, dict] = {}
    for t in trades:
        if t.get("status") != "filled":
            continue
        meta = t.get("meta") if isinstance(t.get("meta"), dict) else {}
        voters = (meta.get("decision") or {}).get("voters") or {}
        sym, side = t["ticker"], t["side"]
        if side == "BUY":
            entry_voters[sym] = [n for n, v in voters.items() if v == "BUY"] or list(voters)
        elif side == "SELL":
            pnl = float(meta.get("realized") or 0.0)   # realized PnL lives in meta
            credit = entry_voters.pop(sym, None) or \
                [n for n, v in voters.items() if v == "SELL"] or list(voters)
            share = pnl / len(credit)
            for name in credit:
                row = by.setdefault(
                    name, {"strategy": name, "round_trips": 0, "pnl": 0.0, "_pnls": []})
                row["round_trips"] += 1
                row["pnl"] += share
                row["_pnls"].append(share)   # per-round-trip credit, for win_rate/expectancy
    ranked = sorted(by.values(), key=lambda d: -d["pnl"])
    for row in ranked:
        pnls = row.pop("_pnls")
        wins = [p for p in pnls if p > 0]
        losses = [p for p in pnls if p < 0]
        gross_loss = -sum(losses)
        row["pnl"] = round(row["pnl"], 4)
        # which strategies actually carry a positive edge, not just total PnL
        row["win_rate"] = round(len(wins) / len(pnls), 4) if pnls else 0.0
        row["expectancy"] = round(row["pnl"] / len(pnls), 4) if pnls else 0.0
        # None (not inf) when there are no losing round-trips — keeps it JSON-safe
        row["profit_factor"] = round(sum(wins) / gross_loss, 3) if gross_loss else None
    return {"by_strategy": ranked}


def sync_orders(state: LiveState, exchange: Optional[str] = None) -> dict:
    """Poll exchange status of submitted (live) orders and settle them locally.

    Maps the venue's status to filled/canceled and fills filled orders into the
    book. Most market orders settle immediately at placement; this covers limit
    orders and partial-fill follow-up.
    """
    from yammyquant.exchanges import get_exchange, default_exchange
    from yammyquant.ops.trading import TradeManager

    ex = get_exchange(exchange or default_exchange())
    tm = TradeManager(state)
    updated = []
    for trade in state.open_orders():
        meta = trade.get("meta") if isinstance(trade.get("meta"), dict) else {}
        oid = meta.get("exchange_order_id")
        if not oid:
            continue
        try:
            status = ex.order_status(oid, trade["ticker"])
        except Exception as exc:
            state.log("sync", f"status check failed for #{trade['id']}: {exc}")
            continue
        raw = str(status.get("status", "")).lower()
        # partial fills: fill the newly-filled delta, keep the order open
        already = float(meta.get("filled_qty", 0.0))
        filled = float(status.get("filled", status.get("executedQty", 0.0)) or 0.0)
        delta = filled - already
        if delta > 1e-12 and raw not in ("filled", "closed"):
            tm._fill_partial(trade, delta)
            state.set_trade_meta(trade["id"], filled_qty=filled)
            updated.append({"id": trade["id"], "status": "partial", "filled": filled})
            continue
        if raw in ("filled", "closed"):
            remaining = trade["quantity"] - already
            if remaining > 1e-12:
                tm._fill(trade["id"], trade["ticker"], trade["side"], remaining, trade["price"])
            else:
                state.set_trade_status(trade["id"], "filled")
            updated.append({"id": trade["id"], "status": "filled"})
        elif raw in ("canceled", "cancelled", "expired", "rejected"):
            state.set_trade_status(trade["id"], "rejected")
            updated.append({"id": trade["id"], "status": "rejected"})
    state.log("sync", f"synced {len(updated)} order(s)")
    return {"exchange": ex.name, "updated": updated, "open_orders": state.open_orders()}


def reconcile(state: LiveState, exchange: Optional[str] = None) -> dict:
    """Compare local positions to the exchange's reported balances (read-only)."""
    from yammyquant.exchanges import get_exchange, default_exchange

    ex = get_exchange(exchange or default_exchange())
    try:
        balances = ex.balances()
    except Exception as exc:
        return {"exchange": ex.name, "error": str(exc),
                "state_positions": state.positions()}
    state.log("reconcile", f"reconciled against {ex.name}")
    return {"exchange": ex.name, "state_positions": state.positions(),
            "exchange_balances": balances}


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
