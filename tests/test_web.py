import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from yammyquant.data.candle import Candle
from yammyquant.data.sources.store import DuckDBStore
from yammyquant.state.store import LiveState
from yammyquant.ops.trading import TradeManager
from yammyquant.web.app import create_app


@pytest.fixture
def client(tmp_path):
    store = DuckDBStore(tmp_path / "store")
    n = 60
    idx = pd.date_range("2023-01-01", periods=n, freq="1D")
    close = 100 + np.arange(n, dtype=float)
    df = pd.DataFrame(
        {"open": close, "high": close + 1, "low": close - 1, "close": close, "volume": [1.0] * n},
        index=idx,
    )
    store.write(Candle("BTCUSDT", df, interval="1d"))
    app = create_app(state_path=str(tmp_path / "s.db"), store_path=str(tmp_path / "store"))
    return TestClient(app), LiveState(tmp_path / "s.db")


def test_state_endpoint(client):
    c, _ = client
    r = c.get("/api/state")
    assert r.status_code == 200
    assert "positions" in r.json()
    assert "live_trading_allowed" in r.json()


def test_candles_endpoint(client):
    c, _ = client
    r = c.get("/api/candles", params={"ticker": "BTCUSDT", "interval": "1d"})
    assert r.status_code == 200
    body = r.json()
    assert len(body["close"]) == 60
    assert len(body["time"]) == 60


def test_candles_missing_404(client):
    c, _ = client
    assert c.get("/api/candles", params={"ticker": "NOPE", "interval": "1d"}).status_code == 404


def test_inbox_post(client):
    c, state = client
    r = c.post("/api/inbox", json={"message": "run a scan"})
    assert r.status_code == 200
    assert state.inbox(only_unread=True)[0]["message"] == "run a scan"


def test_inbox_requires_message(client):
    c, _ = client
    assert c.post("/api/inbox", json={"message": "   "}).status_code == 400


def test_state_endpoint_handles_non_finite_meta(client):
    # profit_factor=inf style values must not break JSON serialization
    c, state = client
    state.log("backtest", "ran", profit_factor=float("inf"), sharpe=float("nan"))
    r = c.get("/api/state")
    assert r.status_code == 200
    meta = r.json()["activity"][0]["meta"]
    assert meta["profit_factor"] is None and meta["sharpe"] is None


def test_strategies_endpoint_and_toggle(client):
    c, _ = client
    items = c.get("/api/strategies").json()
    names = {s["name"] for s in items}
    assert "macross" in names and "donchian_breakout" in names
    assert all(s["enabled"] for s in items)  # default all on
    c.post("/api/settings", json={"key": "strategy.macross.enabled", "value": False})
    items = {s["name"]: s["enabled"] for s in c.get("/api/strategies").json()}
    assert items["macross"] is False


def test_approve_and_reject_pending(client):
    c, state = client
    tm = TradeManager(state)
    tm.cash = 10_000.0
    pending = tm.submit("BTCUSDT", "BUY", 1.0, 100.0, mode="live")
    r = c.post(f"/api/trades/{pending['id']}/reject")
    assert r.status_code == 200 and r.json()["status"] == "rejected"
