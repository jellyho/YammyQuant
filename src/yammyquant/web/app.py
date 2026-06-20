"""The cockpit web app — FastAPI backend + single-page dashboard.

Read-and-control surface over the shared :class:`LiveState`:

* ``GET  /api/state``                  — full cockpit snapshot
* ``GET  /api/candles``                — OHLCV + equity for charting
* ``POST /api/inbox``                  — leave an instruction for the operator
* ``POST /api/trades/{id}/approve``    — approve a pending (live/paper) trade
* ``POST /api/trades/{id}/reject``     — reject a pending trade
* ``POST /api/positions/{ticker}/close`` — flatten a position (paper)
* ``POST /api/settings``               — toggle strategies / flags
* ``WS   /ws``                         — pushes a fresh snapshot on an interval

The frontend is a dependency-free SPA (``static/``) using Plotly via CDN, so
there's no node build step — ``yq dashboard`` just works.
"""

from __future__ import annotations

import asyncio
import json
import math
from pathlib import Path
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.staticfiles import StaticFiles

from yammyquant.state.store import LiveState
from yammyquant.data.sources.store import DuckDBStore
from yammyquant.ops.trading import TradeManager, live_trading_allowed

_STATIC = Path(__file__).parent / "static"


def _json_safe(obj: Any) -> Any:
    """Recursively replace non-finite floats (inf/nan) with None.

    JSON has no representation for infinity/NaN and Starlette serializes with
    ``allow_nan=False``, so any such value anywhere in the state would 500 the
    whole snapshot. Sanitize defensively at the boundary.
    """
    if isinstance(obj, float):
        return obj if math.isfinite(obj) else None
    if isinstance(obj, dict):
        return {k: _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_json_safe(v) for v in obj]
    return obj


def create_app(state_path: str = "yammyquant_state.db", store_path: str = "data_store") -> FastAPI:
    """
    Create and configure a FastAPI application for the YammyQuant Cockpit dashboard.
    
    The application exposes REST endpoints and a WebSocket for reading shared state and issuing control actions. 
    It optionally serves a dependency-free frontend from the static directory.
    
    Parameters:
    	state_path (str): Path to the persistent state database file (default: "yammyquant_state.db")
    	store_path (str): Path to the data store directory (default: "data_store")
    
    Returns:
    	FastAPI: Configured application instance
    """
    app = FastAPI(title="YammyQuant Cockpit")
    state = LiveState(state_path)

    # Surface operator-authored plugins (strategies/indicators) in the dashboard.
    try:
        from yammyquant.plugins import load_plugins
        load_plugins()
    except Exception:
        pass

    def store() -> DuckDBStore:
        return DuckDBStore(store_path)

    # -- REST --------------------------------------------------------------
    @app.get("/api/state")
    def get_state():
        snap = state.snapshot()
        snap["live_trading_allowed"] = live_trading_allowed()
        return _json_safe(snap)

    @app.get("/api/candles")
    def get_candles(ticker: str, interval: str = "1d", limit: int = 300):
        try:
            candle = store().read(ticker, interval)
        except FileNotFoundError:
            raise HTTPException(404, f"no stored candles for {ticker} {interval}")
        candle = candle[-limit:]
        return {
            "ticker": ticker,
            "interval": interval,
            "time": [t.isoformat() for t in candle.index],
            "open": candle.open.tolist(),
            "high": candle.high.tolist(),
            "low": candle.low.tolist(),
            "close": candle.close.tolist(),
            "volume": candle.volume.tolist(),
        }

    @app.post("/api/inbox")
    async def post_inbox(payload: dict):
        message = (payload or {}).get("message", "").strip()
        if not message:
            raise HTTPException(400, "message is required")
        msg_id = state.post_instruction(message)
        return {"id": msg_id, "status": "queued"}

    @app.post("/api/trades/{trade_id}/approve")
    def approve_trade(trade_id: int):
        try:
            return TradeManager(state).approve(trade_id)
        except ValueError as e:
            raise HTTPException(400, str(e))

    @app.post("/api/trades/{trade_id}/reject")
    def reject_trade(trade_id: int):
        try:
            return TradeManager(state).reject(trade_id)
        except ValueError as e:
            raise HTTPException(400, str(e))

    @app.post("/api/positions/{ticker}/close")
    def close_position(ticker: str, payload: dict):
        price = (payload or {}).get("price")
        if price is None:
            raise HTTPException(400, "price is required")
        result = TradeManager(state).close_position(ticker, float(price))
        if result is None:
            raise HTTPException(404, f"no open position for {ticker}")
        return result

    @app.get("/api/settings")
    def get_settings():
        return _json_safe(state.settings())

    @app.post("/api/settings")
    def set_setting(payload: dict):
        key, value = (payload or {}).get("key"), (payload or {}).get("value")
        if not key:
            raise HTTPException(400, "key is required")
        state.set(key, value)
        return {"key": key, "value": value}

    @app.get("/api/plugins")
    def get_plugins():
        from yammyquant.plugins import load_plugins
        return _json_safe(load_plugins())

    @app.post("/api/trade")
    def manual_trade(payload: dict):
        p = payload or {}
        try:
            ticker = p["ticker"].strip()
            side = p["side"]
            quantity = float(p["quantity"])
            price = float(p["price"])
        except (KeyError, ValueError, AttributeError):
            raise HTTPException(400, "ticker, side, quantity, price are required")
        result = TradeManager(state).submit(
            ticker, side, quantity, price, mode=p.get("mode", "paper"),
            rationale=p.get("rationale", "manual (dashboard)"))
        return _json_safe(result)

    @app.post("/api/target")
    def set_targets(payload: dict):
        """Set portfolio target weights, e.g. {"BTCUSDT": 0.5, "ETHUSDT": 0.3}."""
        targets = {k: float(v) for k, v in (payload or {}).items()}
        state.set("targets", targets)
        return {"targets": targets}

    @app.post("/api/rebalance")
    def rebalance(payload: dict):
        from yammyquant.ops import operator as ops
        execute = bool((payload or {}).get("execute", False))
        try:
            return _json_safe(ops.rebalance(store(), state, execute=execute,
                                            mode=state.get("trade_mode", "paper")))
        except Exception as e:
            raise HTTPException(502, f"rebalance failed: {e}")

    @app.post("/api/cycle")
    def run_cycle():
        from yammyquant.ops import operator as ops
        try:
            return _json_safe(ops.run_cycle(store(), state))
        except Exception as e:
            raise HTTPException(502, f"cycle failed: {e}")

    @app.post("/api/notify")
    def push_status():
        from yammyquant.ops import operator as ops
        return _json_safe(ops.notify_status(state))

    @app.post("/api/journal")
    def post_journal(payload: dict):
        text = (payload or {}).get("text", "").strip()
        if not text:
            raise HTTPException(400, "text is required")
        return {"id": state.add_journal(text, tag=(payload or {}).get("tag", ""))}

    @app.post("/api/watch")
    def add_watch(payload: dict):
        symbol = (payload or {}).get("symbol", "").strip()
        if not symbol:
            raise HTTPException(400, "symbol is required")
        state.add_watch(symbol, (payload or {}).get("exchange", ""),
                        (payload or {}).get("interval", "1d"), (payload or {}).get("note", ""))
        return _json_safe(state.watchlist())

    @app.delete("/api/watch/{symbol}")
    def remove_watch(symbol: str):
        state.remove_watch(symbol)
        return _json_safe(state.watchlist())

    @app.get("/api/risk")
    def get_risk():
        from yammyquant.ops.risk_policy import AccountRiskPolicy
        from dataclasses import asdict
        return asdict(AccountRiskPolicy.load(state))

    @app.post("/api/risk")
    def set_risk(payload: dict):
        from yammyquant.ops.risk_policy import AccountRiskPolicy
        from dataclasses import asdict
        policy = AccountRiskPolicy.load(state)
        for key, value in (payload or {}).items():
            if hasattr(policy, key):
                setattr(policy, key, None if value in (None, "", "none") else float(value))
        policy.save(state)
        return asdict(policy)

    @app.get("/api/report")
    def get_report():
        """
        Retrieve the operational report.
        
        Returns:
        	A dictionary containing the operational report, with non-finite floats converted to None.
        """
        from yammyquant.ops import operator as ops
        return _json_safe(ops.report(state))

    @app.post("/api/news/collect")
    def collect_news():
        """
        Collect financial news data.
        
        Returns:
            dict: A JSON-safe dictionary containing the collected news.
        
        Raises:
            HTTPException: HTTP 502 error if news collection fails.
        """
        from yammyquant.ops import operator as ops
        try:
            return _json_safe(ops.collect_news(state))
        except Exception as e:
            raise HTTPException(502, f"news collect failed: {e}")

    @app.get("/api/decide")
    def preview_decide():
        """
        Preview trading decisions without executing them.
        
        Returns:
        	Decision preview data.
        
        Raises:
        	HTTPException: 502 status if the decision operation fails.
        """
        from yammyquant.ops import operator as ops
        try:
            return _json_safe(ops.decide(store(), state, execute=False))
        except Exception as e:
            raise HTTPException(502, f"decide failed: {e}")

    @app.post("/api/decide")
    def run_decide(payload: dict):
        from yammyquant.ops import operator as ops
        mode = (payload or {}).get("mode", "paper")
        try:
            return _json_safe(ops.decide(store(), state, mode=mode, execute=True))
        except Exception as e:
            raise HTTPException(502, f"decide failed: {e}")

    @app.get("/api/strategies")
    def get_strategies():
        from yammyquant.ops.operator import STRATEGIES
        settings = state.settings()
        return [
            {"name": name,
             "enabled": settings.get(f"strategy.{name}.enabled", True),
             "weight": float(settings.get(f"strategy.{name}.weight", 1.0))}
            for name in sorted(STRATEGIES)
        ]

    @app.post("/api/backtest")
    def run_backtest(payload: dict):
        from yammyquant.ops import operator as ops
        p = payload or {}
        try:
            return _json_safe(ops.backtest(
                store(), p["ticker"], p.get("interval", "1d"), p["strategy"],
                params=p.get("params") or None, state=state))
        except KeyError:
            raise HTTPException(400, "ticker and strategy are required")
        except Exception as e:
            raise HTTPException(502, f"backtest failed: {e}")

    @app.post("/api/optimize")
    def run_optimize(payload: dict):
        from yammyquant.ops import operator as ops
        p = payload or {}
        try:
            return _json_safe(ops.optimize(
                store(), p["ticker"], p.get("interval", "1d"), p["strategy"],
                metric=p.get("metric", "sharpe"),
                walk_forward_splits=int(p.get("walk_forward", 0)), state=state))
        except KeyError:
            raise HTTPException(400, "ticker and strategy are required")
        except Exception as e:
            raise HTTPException(502, f"optimize failed: {e}")

    # -- WebSocket: push state snapshots -----------------------------------
    @app.websocket("/ws")
    async def ws(websocket: WebSocket):
        await websocket.accept()
        try:
            while True:
                snap = state.snapshot()
                snap["live_trading_allowed"] = live_trading_allowed()
                await websocket.send_text(json.dumps(_json_safe(snap), default=str, allow_nan=False))
                await asyncio.sleep(2.0)
        except WebSocketDisconnect:
            return

    # -- static SPA --------------------------------------------------------
    if _STATIC.exists():
        app.mount("/", StaticFiles(directory=str(_STATIC), html=True), name="static")

    return app


def serve(host: str = "127.0.0.1", port: int = 8000,
          state_path: str = "yammyquant_state.db", store_path: str = "data_store") -> None:
    import uvicorn

    print(f"YammyQuant cockpit → http://{host}:{port}")
    print(f"  state: {state_path}   store: {store_path}   live trading: {live_trading_allowed()}")
    uvicorn.run(create_app(state_path, store_path), host=host, port=port)
