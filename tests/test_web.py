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


def test_journal_endpoint(client):
    c, state = client
    assert c.post("/api/journal", json={"text": "thesis", "tag": "t"}).status_code == 200
    assert state.journal()[0]["text"] == "thesis"
    assert c.post("/api/journal", json={"text": "  "}).status_code == 400


def test_watch_add_and_remove(client):
    c, state = client
    c.post("/api/watch", json={"symbol": "BTCUSDT", "interval": "1d"})
    assert "BTCUSDT" in [w["symbol"] for w in state.watchlist()]
    c.delete("/api/watch/BTCUSDT")
    assert state.watchlist() == []


def test_risk_get_set(client):
    c, _ = client
    c.post("/api/risk", json={"max_open_positions": 5, "daily_loss_limit": 200})
    risk = c.get("/api/risk").json()
    assert risk["max_open_positions"] == 5 and risk["daily_loss_limit"] == 200


def test_report_endpoint(client):
    c, _ = client
    assert "realized_pnl" in c.get("/api/report").json()


def test_news_in_snapshot(client):
    c, state = client
    state.add_news("BTC rallies", url="http://a", symbol="BTCUSDT", sentiment=0.6, source="t")
    snap = c.get("/api/state").json()
    assert "news" in snap and snap["news"][0]["title"] == "BTC rallies"


def test_decide_preview_empty_watchlist(client):
    # empty watchlist => no exchange calls => safe dry-run preview
    c, _ = client
    r = c.get("/api/decide")
    assert r.status_code == 200
    assert r.json()["proposals"] == []
    assert r.json()["execute"] is False


def test_approve_and_reject_pending(client):
    c, state = client
    tm = TradeManager(state)
    tm.cash = 10_000.0
    pending = tm.submit("BTCUSDT", "BUY", 1.0, 100.0, mode="live")
    r = c.post(f"/api/trades/{pending['id']}/reject")
    assert r.status_code == 200 and r.json()["status"] == "rejected"


def test_settings_get_and_plugins(client):
    c, _ = client
    assert c.get("/api/settings").status_code == 200
    pj = c.get("/api/plugins").json()
    assert "strategies" in pj and "errors" in pj


def test_manual_trade_endpoint(client):
    c, state = client
    r = c.post("/api/trade", json={"ticker": "BTCUSDT", "side": "BUY",
                                   "quantity": 0.1, "price": 100, "mode": "paper"})
    assert r.status_code == 200 and r.json()["status"] == "filled"
    assert state.positions()[0]["ticker"] == "BTCUSDT"


def test_manual_trade_validates(client):
    c, _ = client
    assert c.post("/api/trade", json={"ticker": "BTCUSDT"}).status_code == 400


def test_correlation_endpoint(client):
    c, _ = client
    # one symbol seeded -> need >=2 -> 502
    assert c.post("/api/correlation", json={"symbols": ["BTCUSDT"]}).status_code == 502
    assert c.post("/api/correlation", json={}).status_code == 400


def test_risk_parity_endpoint(client):
    c, state = client
    r = c.post("/api/target/risk-parity", json={"symbols": ["BTCUSDT"]})
    assert r.status_code == 200
    assert r.json()["targets"]["BTCUSDT"] == 1.0   # single symbol -> all weight
    assert state.get("targets")["BTCUSDT"] == 1.0


def test_targets_and_cycle_and_status(client):
    c, state = client
    assert c.post("/api/target", json={"BTCUSDT": 0.5}).json()["targets"]["BTCUSDT"] == 0.5
    assert state.get("targets") == {"BTCUSDT": 0.5}
    assert c.post("/api/notify").status_code == 200          # log-only (no webhook)
    state.add_watch("BTCUSDT", "", "1d")
    assert c.post("/api/cycle").status_code == 200


def test_backtest_endpoint(client):
    c, _ = client
    r = c.post("/api/backtest", json={"ticker": "BTCUSDT", "interval": "1d",
                                      "strategy": "macross", "params": {"fast": 3, "slow": 8}})
    assert r.status_code == 200 and "sharpe" in r.json()


def test_optimize_endpoint(client):
    c, _ = client
    r = c.post("/api/optimize", json={"ticker": "BTCUSDT", "interval": "1d",
                                      "strategy": "macross"})
    assert r.status_code == 200 and "best_params" in r.json()


def test_optimize_walkforward_returns_folds(tmp_path):
    # walk-forward needs enough bars per fold, so build a larger local store
    store = DuckDBStore(tmp_path / "store")
    rng = np.random.default_rng(1)
    close = 100 * np.exp(np.cumsum(rng.normal(0.0005, 0.02, 600)))
    idx = pd.date_range("2022-01-01", periods=600, freq="1D")
    store.write(Candle("BTCUSDT", pd.DataFrame(
        {"open": close, "high": close * 1.01, "low": close * 0.99, "close": close,
         "volume": rng.uniform(800, 2200, 600)}, index=idx), interval="1d"))
    app = create_app(state_path=str(tmp_path / "s.db"), store_path=str(tmp_path / "store"))
    c = TestClient(app)
    r = c.post("/api/optimize", json={"ticker": "BTCUSDT", "interval": "1d",
                                      "strategy": "macross", "walk_forward": 3})
    body = r.json()
    assert r.status_code == 200 and body["n_folds"] >= 1
    assert all({"fold", "in_sample_score", "out_of_sample"} <= set(f) for f in body["folds"])


def test_optimize_walkforward_insufficient_data_errors(client):
    # too few bars per fold -> clear 502, not a crash
    c, _ = client
    r = c.post("/api/optimize", json={"ticker": "BTCUSDT", "interval": "1d",
                                      "strategy": "macross", "walk_forward": 3})
    assert r.status_code == 502


def test_backtest_requires_fields(client):
    c, _ = client
    assert c.post("/api/backtest", json={"interval": "1d"}).status_code == 400


def test_strategies_endpoint_includes_weight(client):
    c, _ = client
    assert all("weight" in s for s in c.get("/api/strategies").json())


def test_attribution_endpoint(client):
    c, _ = client
    r = c.get("/api/attribution")
    assert r.status_code == 200 and "by_strategy" in r.json()


def test_backtest_returns_equity_curve(client):
    c, _ = client
    r = c.post("/api/backtest", json={"ticker": "BTCUSDT", "interval": "1d",
                                      "strategy": "macross", "params": {"fast": 3, "slow": 8}})
    body = r.json()
    assert r.status_code == 200 and isinstance(body.get("equity"), list)
    # price series + trade markers for the signals overlay
    assert body["price"] and all({"ts", "close"} <= set(pt) for pt in body["price"])
    assert all({"ts", "side", "price"} <= set(t) for t in body["trades"])
    # underwater drawdown series: every point carries a non-positive dd,
    # and its trough equals the reported max_drawdown stat
    dds = [pt["dd"] for pt in body["equity"]]
    assert all(d <= 1e-9 for d in dds)
    assert min(dds) == pytest.approx(body["max_drawdown"], abs=1e-4)


def test_plugin_web_authoring(client, tmp_path, monkeypatch):
    c, _ = client
    monkeypatch.setenv("YQ_PLUGINS_DIR", str(tmp_path / "uplugins"))
    r = c.post("/api/plugins/new", json={"kind": "strategy", "name": "web_edge"})
    assert r.status_code == 200
    files = c.get("/api/plugins/files").json()
    assert any("web_edge" in f["path"] for f in files)
    path = next(f["path"] for f in files if "web_edge" in f["path"])
    content = c.get("/api/plugins/file", params={"path": path}).json()["content"]
    assert "web_edge" in content
    assert c.post("/api/plugins/file", json={"path": path, "content": content}).status_code == 200


def test_plugin_path_traversal_blocked(client, tmp_path, monkeypatch):
    c, _ = client
    monkeypatch.setenv("YQ_PLUGINS_DIR", str(tmp_path / "uplugins"))
    assert c.get("/api/plugins/file", params={"path": "../../etc/passwd"}).status_code == 400


def test_portfolio_endpoint(client):
    c, _ = client
    r = c.post("/api/portfolio", json={"symbols": ["BTCUSDT"], "interval": "1d",
                                       "strategy": "macross"})
    assert r.status_code == 200
    body = r.json()
    assert "portfolio" in body and "BTCUSDT" in body["per_symbol"]


def test_portfolio_requires_symbols(client):
    c, _ = client
    assert c.post("/api/portfolio", json={"strategy": "macross"}).status_code == 400
