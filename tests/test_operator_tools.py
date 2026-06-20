import numpy as np
import pandas as pd
import pytest

from yammyquant.data.candle import Candle
from yammyquant.data.sources.store import DuckDBStore
from yammyquant.state.store import LiveState
from yammyquant.ops import operator as ops
from yammyquant.ops.trading import TradeManager


class FakeExchange:
    name = "fake"

    def last_price(self, ticker, interval="1m"):
        return 120.0

    def read(self, ticker, interval="1d", count=200, start=None, end=None):
        n = 60
        idx = pd.date_range("2023-01-01", periods=n, freq="1D")
        close = 100 + np.arange(n, dtype=float)
        df = pd.DataFrame(
            {"open": close, "high": close + 1, "low": close - 1, "close": close,
             "volume": [1.0] * n},
            index=idx,
        )
        return Candle(ticker.replace("/", ""), df, interval=interval)

    def balances(self):
        return {"FAKE": {"free": 1.0}}


@pytest.fixture
def fake_exchange(monkeypatch):
    fake = FakeExchange()
    monkeypatch.setattr("yammyquant.exchanges.get_exchange", lambda name=None, **k: fake)
    monkeypatch.setattr("yammyquant.exchanges.default_exchange", lambda: "fake")
    return fake


def _seed_store(tmp_path, stale=False):
    store = DuckDBStore(tmp_path / "store")
    end = "2020-01-01" if stale else pd.Timestamp.now('UTC').strftime("%Y-%m-%d")
    idx = pd.date_range(end=end, periods=40, freq="1D")
    close = 100 + np.arange(40, dtype=float)
    df = pd.DataFrame(
        {"open": close, "high": close + 1, "low": close - 1, "close": close, "volume": [1.0] * 40},
        index=idx,
    )
    store.write(Candle("BTCUSDT", df, interval="1d"))
    return store


def test_mark_records_equity(tmp_path, fake_exchange):
    state = LiveState(tmp_path / "s.db")
    tm = TradeManager(state, fee=0.0)
    tm.cash = 10_000.0
    tm.submit("BTCUSDT", "BUY", 1.0, 100.0)         # cash 9900, 1 unit @100
    out = ops.mark(state)                            # fake price 120
    assert out["prices"]["BTCUSDT"] == 120.0
    assert out["equity"] == pytest.approx(9900.0 + 120.0)


def test_doctor_flags_no_cash_and_fresh_data(tmp_path):
    store = _seed_store(tmp_path, stale=False)
    state = LiveState(tmp_path / "s.db")
    rep = ops.doctor(store, state)
    assert "cash not initialized (set via a paper trade or config)" in rep["issues"]
    assert any(d["ticker"] == "BTCUSDT" and not d["stale"] for d in rep["data_freshness"])


def test_doctor_detects_stale_data(tmp_path):
    store = _seed_store(tmp_path, stale=True)
    state = LiveState(tmp_path / "s.db")
    state.set("cash", 10_000.0)
    rep = ops.doctor(store, state)
    assert any(d["stale"] for d in rep["data_freshness"])
    assert rep["ok"] is False


def test_run_cycle_refreshes_and_scans(tmp_path, fake_exchange):
    store = DuckDBStore(tmp_path / "store")
    state = LiveState(tmp_path / "s.db")
    state.add_watch("BTCUSDT", "fake", "1d")
    out = ops.run_cycle(store, state)
    assert "BTCUSDT" in out["refreshed"]
    assert isinstance(out["signals"], list)
    assert len(store.read("BTCUSDT", "1d")) == 60  # data was written


def test_report_realized_pnl(tmp_path):
    state = LiveState(tmp_path / "s.db")
    tm = TradeManager(state, fee=0.0)
    tm.cash = 10_000.0
    tm.submit("AAA", "BUY", 10, 100)
    tm.submit("AAA", "SELL", 10, 120)               # +200 realized
    rep = ops.report(state)
    assert rep["realized_pnl"] == pytest.approx(200.0)
    assert rep["closed_trades"] == 1
    assert rep["realized_by_symbol"]["AAA"] == pytest.approx(200.0)


def test_decide_proposes_buy_dry_run(tmp_path, fake_exchange):
    store = DuckDBStore(tmp_path / "store")
    state = LiveState(tmp_path / "s.db")
    state.set("cash", 10_000.0)
    state.add_watch("BTCUSDT", "fake", "1d")
    out = ops.decide(store, state, weight=0.2, execute=False)
    # rising series -> donchian/macross give a BUY; flat book -> entry proposed
    buys = [p for p in out["proposals"] if p["side"] == "BUY"]
    assert buys and buys[0]["symbol"] == "BTCUSDT"
    assert out["proposals"][0].get("status") is None  # dry run, not executed
    assert state.trades() == []


def test_decide_executes_paper(tmp_path, fake_exchange):
    store = DuckDBStore(tmp_path / "store")
    state = LiveState(tmp_path / "s.db")
    state.set("cash", 10_000.0)
    state.add_watch("BTCUSDT", "fake", "1d")
    out = ops.decide(store, state, weight=0.2, execute=True, mode="paper")
    assert any(p.get("status") == "filled" for p in out["proposals"])
    assert state.positions()  # a position was opened


def test_sync_orders_settles_submitted(tmp_path):
    state = LiveState(tmp_path / "s.db")
    from yammyquant.ops.trading import TradeManager
    TradeManager(state).cash = 10_000.0
    tid = state.add_trade("BTCUSDT", "BUY", 1.0, 100.0, "live", "submitted", "")
    state.set_trade_meta(tid, exchange_order_id="OID1")

    class _Ex:
        name = "fake"
        def order_status(self, oid, ticker):
            return {"status": "filled"}

    monkeypatch_target = "yammyquant.exchanges.get_exchange"
    import pytest as _pytest
    with _pytest.MonkeyPatch.context() as mp:
        mp.setattr(monkeypatch_target, lambda name=None, **k: _Ex())
        mp.setattr("yammyquant.exchanges.default_exchange", lambda: "fake")
        out = ops.sync_orders(state)
    assert out["updated"] == [{"id": tid, "status": "filled"}]
    assert state.get_trade(tid)["status"] == "filled"
    assert state.positions()[0]["ticker"] == "BTCUSDT"


def test_scheduler_runs_n_cycles(tmp_path, fake_exchange):
    from yammyquant.ops.scheduler import run_loop
    state = LiveState(tmp_path / "s.db")
    state.add_watch("BTCUSDT", "fake", "1d")
    calls = []
    n = run_loop(str(tmp_path / "s.db"), str(tmp_path / "store"),
                 interval_seconds=0, max_cycles=2, sleep=lambda s: calls.append(s))
    assert n == 2


def test_portfolio_backtest(tmp_path):
    import numpy as np
    import pandas as pd
    from yammyquant.data.sources.store import DuckDBStore
    from yammyquant.data.candle import Candle
    from yammyquant.ops import operator as ops

    store = DuckDBStore(tmp_path / "store")
    for sym, seed in (("AAA", 1), ("BBB", 2)):
        rng = np.random.default_rng(seed)
        close = 100 * np.exp(np.cumsum(rng.normal(0, 0.02, 150)))
        idx = pd.date_range("2023-01-01", periods=150, freq="1D")
        df = pd.DataFrame({"open": close, "high": close * 1.01, "low": close * 0.99,
                           "close": close, "volume": np.full(150, 1000.0)}, index=idx)
        store.write(Candle(sym, df, interval="1d"))

    out = ops.portfolio_backtest(store, ["AAA", "BBB"], "1d", "macross")
    assert set(out["per_symbol"]) == {"AAA", "BBB"}
    assert abs(sum(s["weight"] for s in out["per_symbol"].values()) - 1.0) < 1e-9
    assert "sharpe" in out["portfolio"] and out["equity"]
    # combined start equity ≈ the 10k total cash
    assert abs(out["equity"][0]["equity"] - 10_000) < 1.0


def test_attribution_credits_entry_voters(tmp_path):
    state = LiveState(tmp_path / "s.db")
    tm = TradeManager(state, fee=0.0)
    tm.cash = 10_000.0
    tm.submit("AAA", "BUY", 1.0, 100, context={"voters": {"macross": "BUY", "supertrend": "BUY"}})
    tm.submit("AAA", "SELL", 1.0, 130, context={"voters": {"macross": "SELL"}})   # +30
    attr = {r["strategy"]: r for r in ops.attribution(state)["by_strategy"]}
    # +30 realized split across the two entry voters
    assert attr["macross"]["pnl"] == pytest.approx(15.0)
    assert attr["supertrend"]["pnl"] == pytest.approx(15.0)
    assert attr["macross"]["round_trips"] == 1
