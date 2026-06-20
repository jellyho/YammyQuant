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
                   for r in res.results[:5]]}
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


def doctor(store: DuckDBStore, state: LiveState, stale_factor: float = 3.0) -> dict:
    """Health check: data freshness, config completeness, account sanity."""
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

    return {
        "ok": not issues,
        "issues": issues,
        "data_freshness": data,
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
    return {"refreshed": refreshed, "signals": signals, "equity": equity, "decisions": decisions}


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
                buyers = sum(v == "BUY" for v in votes)
                reason = (f"entry signal — {rule} vote score {agg['score']} "
                          f"({buyers} of {len(votes)} buy); size {target_w:.0%} of equity "
                          f"(≈{equity * target_w:,.0f})")
                if gate is not None:
                    reason += f"; sentiment {senti}"
                    context["sentiment"] = senti
                context["weight"] = target_w
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
    from yammyquant.metrics.performance import max_drawdown, sharpe, _BARS_PER_YEAR

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

    out = {
        "equity_start": round(float(equity.iloc[0]), 2) if len(equity) else None,
        "equity_now": round(float(equity.iloc[-1]), 2) if len(equity) else None,
        "total_return": round(float(equity.iloc[-1] / equity.iloc[0] - 1), 4)
                        if len(equity) > 1 and equity.iloc[0] else 0.0,
        "max_drawdown": round(max_drawdown(equity), 4) if len(equity) else 0.0,
        "sharpe": round(sharpe(rets, ppy), 3),
        "realized_pnl": round(sum(realized), 4),
        "closed_trades": len(realized),
        "win_rate": round(len(wins) / len(realized), 4) if realized else 0.0,
        "profit_factor": round(sum(wins) / abs(sum(losses)), 3) if losses else None,
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
    if pending:
        parts.append(f"⏳ {len(pending)} pending approval(s)")
    message = "📊 status — " + " · ".join(str(p) for p in parts)
    sent = notify(state, message, "info")
    return {"message": message, "sent": sent, "channels": channels()}


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
