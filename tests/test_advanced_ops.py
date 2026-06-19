"""Advanced operation: rebalancing, decay tracking, limit orders + partial fills."""

import numpy as np
import pandas as pd
import pytest

from yammyquant.data.candle import Candle
from yammyquant.data.sources.store import DuckDBStore
from yammyquant.state.store import LiveState
from yammyquant.ops import operator as ops
from yammyquant.ops.trading import TradeManager


class PriceExchange:
    name = "fake"

    def __init__(self, prices):
        self.prices = prices

    def last_price(self, ticker, interval="1m"):
        return self.prices[ticker]


@pytest.fixture
def price_exchange(monkeypatch):
    ex = PriceExchange({"AAA": 100.0, "BBB": 50.0})
    monkeypatch.setattr("yammyquant.exchanges.get_exchange", lambda name=None, **k: ex)
    monkeypatch.setattr("yammyquant.exchanges.default_exchange", lambda: "fake")
    return ex


# -- rebalancing -----------------------------------------------------------
def test_rebalance_buys_toward_targets(tmp_path, price_exchange):
    store = DuckDBStore(tmp_path / "store")
    state = LiveState(tmp_path / "s.db")
    state.set("cash", 10_000.0)
    state.set("targets", {"AAA": 0.5, "BBB": 0.5})
    out = ops.rebalance(store, state, execute=True, mode="paper")
    sides = {o["symbol"]: o for o in out["orders"]}
    assert sides["AAA"]["side"] == "BUY" and sides["BBB"]["side"] == "BUY"
    # ~5000 each: 50 units AAA @100, 100 units BBB @50
    assert sides["AAA"]["quantity"] == pytest.approx(50.0, rel=0.05)
    assert sides["BBB"]["quantity"] == pytest.approx(100.0, rel=0.05)


def test_rebalance_within_band_no_orders(tmp_path, price_exchange):
    store = DuckDBStore(tmp_path / "store")
    state = LiveState(tmp_path / "s.db")
    tm = TradeManager(state, fee=0.0)
    tm.cash = 10_000.0
    tm.submit("AAA", "BUY", 50, 100)   # 5000 of 10000 equity = 50%
    state.set("targets", {"AAA": 0.5})
    out = ops.rebalance(store, state, band=0.05, execute=False)
    assert out["orders"] == []


def test_rebalance_no_targets(tmp_path, price_exchange):
    store = DuckDBStore(tmp_path / "store")
    state = LiveState(tmp_path / "s.db")
    assert ops.rebalance(store, state)["orders"] == []


# -- strategy decay --------------------------------------------------------
def _seed(tmp_path):
    store = DuckDBStore(tmp_path / "store")
    n = 200
    idx = pd.date_range("2023-01-01", periods=n, freq="1D")
    close = 100 + 10 * np.sin(np.arange(n) / 8.0)
    df = pd.DataFrame(
        {"open": close, "high": close + 1, "low": close - 1, "close": close, "volume": [1.0] * n},
        index=idx,
    )
    store.write(Candle("BTCUSDT", df, interval="1d"))
    return store


def test_record_expectation_and_decay(tmp_path):
    store = _seed(tmp_path)
    state = LiveState(tmp_path / "s.db")
    ops.record_expectation(store, state, "BTCUSDT", "1d", "macross", {"fast": 5, "slow": 20})
    exp = state.get("expectations")
    assert "macross:BTCUSDT:1d" in exp
    # no equity history yet -> realized sharpe 0 -> flagged decayed if expected>0
    result = ops.decay_check(state)
    assert "checks" in result and len(result["checks"]) == 1


# -- limit orders + partial fills -----------------------------------------
def test_live_limit_order_rests_as_submitted(tmp_path, monkeypatch):
    monkeypatch.setenv("YQ_ALLOW_LIVE", "1")
    state = LiveState(tmp_path / "s.db")
    tm = TradeManager(state, fee=0.0)
    tm.cash = 10_000.0
    pending = tm.submit("BTCUSDT", "BUY", 1.0, 100.0, mode="live", order_type="limit")
    tm.approve(pending["id"], place_live=lambda t: {"id": "OID9"})
    trade = state.get_trade(pending["id"])
    assert trade["status"] == "submitted"        # limit rests, not filled
    assert state.positions() == []


def test_sync_partial_then_full(tmp_path, monkeypatch):
    state = LiveState(tmp_path / "s.db")
    TradeManager(state).cash = 10_000.0
    tid = state.add_trade("BTCUSDT", "BUY", 2.0, 100.0, "live", "submitted", "", order_type="limit")
    state.set_trade_meta(tid, exchange_order_id="OID")

    seq = [{"status": "open", "filled": 1.0}, {"status": "closed", "filled": 2.0}]

    class _Ex:
        name = "fake"
        def order_status(self, oid, ticker):
            return seq.pop(0)

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("yammyquant.exchanges.get_exchange", lambda name=None, **k: _Ex())
        mp.setattr("yammyquant.exchanges.default_exchange", lambda: "fake")
        first = ops.sync_orders(state)
        assert first["updated"][0]["status"] == "partial"
        assert state.positions()[0]["quantity"] == pytest.approx(1.0)
        second = ops.sync_orders(state)
        assert second["updated"][0]["status"] == "filled"
    assert state.positions()[0]["quantity"] == pytest.approx(2.0)
    assert state.get_trade(tid)["status"] == "filled"
