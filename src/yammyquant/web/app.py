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
from typing import Any, Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.responses import JSONResponse
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
    app = FastAPI(title="YammyQuant Cockpit")
    state = LiveState(state_path)

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

    @app.post("/api/settings")
    def set_setting(payload: dict):
        key, value = (payload or {}).get("key"), (payload or {}).get("value")
        if not key:
            raise HTTPException(400, "key is required")
        state.set(key, value)
        return {"key": key, "value": value}

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
        from yammyquant.ops import operator as ops
        return _json_safe(ops.report(state))

    @app.post("/api/news/collect")
    def collect_news():
        from yammyquant.ops import operator as ops
        try:
            return _json_safe(ops.collect_news(state))
        except Exception as e:
            raise HTTPException(502, f"news collect failed: {e}")

    @app.get("/api/decide")
    def preview_decide():
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
            {"name": name, "enabled": settings.get(f"strategy.{name}.enabled", True)}
            for name in sorted(STRATEGIES)
        ]

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
