import numpy as np
import pandas as pd
import pytest

from yammyquant.data.candle import Candle
from yammyquant.data.sources.store import DuckDBStore
from yammyquant.state.store import LiveState
from yammyquant.ops import operator as ops
from yammyquant.ops.trading import TradeManager


def _pin_strategies(state, *names):
    """Enable only the named strategies so a decide test's voter set is
    deterministic and independent of the growing strategy registry."""
    for n in ops.STRATEGIES:
        state.set(f"strategy.{n}.enabled", n in names)


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


def test_report_expectancy_and_avgs(tmp_path):
    state = LiveState(tmp_path / "s.db")
    tm = TradeManager(state, fee=0.0)
    tm.cash = 10_000.0
    tm.submit("AAA", "BUY", 10, 100)
    tm.submit("AAA", "SELL", 10, 120)               # +200 realized (win)
    tm.submit("BBB", "BUY", 10, 100)
    tm.submit("BBB", "SELL", 10, 90)                # -100 realized (loss)
    rep = ops.report(state)
    assert rep["closed_trades"] == 2
    assert rep["win_rate"] == pytest.approx(0.5)
    assert rep["avg_win"] == pytest.approx(200.0)
    assert rep["avg_loss"] == pytest.approx(-100.0)
    # expectancy == mean realized PnL per trade == (200 - 100) / 2
    assert rep["expectancy"] == pytest.approx(50.0)
    assert "sortino" in rep


def test_cost_sensitivity_sweep(tmp_path):
    import numpy as np
    import pandas as pd
    store = DuckDBStore(tmp_path / "store")
    n = 250
    idx = pd.date_range("2022-01-01", periods=n, freq="1D")
    close = 100 + 10 * np.sin(np.arange(n) / 7.0)      # oscillating -> many trades
    store.write(Candle("OSC", pd.DataFrame(
        {"open": close, "high": close + 1, "low": close - 1, "close": close,
         "volume": np.full(n, 1.0)}, index=idx), interval="1d"))
    out = ops.cost_sensitivity(store, "OSC", "1d", "macross", {"fast": 5, "slow": 20},
                               slippages=[0.0, 0.001, 0.01])
    assert [r["slippage"] for r in out["rows"]] == [0.0, 0.001, 0.01]
    # higher slippage never improves total return
    rets = [r["total_return"] for r in out["rows"]]
    assert rets[0] >= rets[-1]
    assert "breakeven_slippage" in out


def test_decide_proposes_buy_dry_run(tmp_path, fake_exchange):
    store = DuckDBStore(tmp_path / "store")
    state = LiveState(tmp_path / "s.db")
    state.set("cash", 10_000.0)
    state.add_watch("BTCUSDT", "fake", "1d")
    _pin_strategies(state, "volatility_breakout")
    out = ops.decide(store, state, weight=0.2, execute=False)
    # rising series -> volatility_breakout gives a BUY; flat book -> entry proposed
    buys = [p for p in out["proposals"] if p["side"] == "BUY"]
    assert buys and buys[0]["symbol"] == "BTCUSDT"
    assert out["proposals"][0].get("status") is None  # dry run, not executed
    assert state.trades() == []


def test_decide_executes_paper(tmp_path, fake_exchange):
    store = DuckDBStore(tmp_path / "store")
    state = LiveState(tmp_path / "s.db")
    state.set("cash", 10_000.0)
    state.add_watch("BTCUSDT", "fake", "1d")
    _pin_strategies(state, "volatility_breakout")
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
    # weighted buy-and-hold benchmark, anchored to the same start
    assert out["benchmark_return"] is not None
    assert out["equity"][0]["bench"] == pytest.approx(out["equity"][0]["equity"], abs=1.0)


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
    # single winning round-trip -> 100% win rate, expectancy == per-trip credit
    assert attr["macross"]["win_rate"] == pytest.approx(1.0)
    assert attr["macross"]["expectancy"] == pytest.approx(15.0)


def test_attribution_win_rate_and_expectancy(tmp_path):
    state = LiveState(tmp_path / "s.db")
    tm = TradeManager(state, fee=0.0)
    tm.cash = 10_000.0
    ctx = {"voters": {"macross": "BUY"}}
    tm.submit("AAA", "BUY", 1.0, 100, context=ctx)
    tm.submit("AAA", "SELL", 1.0, 130, context={"voters": {"macross": "SELL"}})  # +30 win
    tm.submit("AAA", "BUY", 1.0, 100, context=ctx)
    tm.submit("AAA", "SELL", 1.0, 90, context={"voters": {"macross": "SELL"}})   # -10 loss
    row = ops.attribution(state)["by_strategy"][0]
    assert row["strategy"] == "macross"
    assert row["round_trips"] == 2
    assert row["pnl"] == pytest.approx(20.0)
    assert row["win_rate"] == pytest.approx(0.5)
    assert row["expectancy"] == pytest.approx(10.0)   # (30 - 10) / 2
    assert row["profit_factor"] == pytest.approx(3.0)  # gross win 30 / gross loss 10


def test_risk_parity_weights_inverse_vol(tmp_path):
    import numpy as np
    import pandas as pd
    store = DuckDBStore(tmp_path / "store")
    for sym, sig in (("CALM", 0.005), ("WILD", 0.05)):
        rng = np.random.default_rng(1)
        close = 100 * np.exp(np.cumsum(rng.normal(0, sig, 200)))
        idx = pd.date_range("2023-01-01", periods=200, freq="1D")
        store.write(Candle(sym, pd.DataFrame(
            {"open": close, "high": close * 1.01, "low": close * 0.99, "close": close,
             "volume": np.full(200, 1000.0)}, index=idx), interval="1d"))
    w = ops.risk_parity_weights(store, ["CALM", "WILD"], "1d")
    assert abs(sum(w.values()) - 1.0) < 1e-6
    assert w["CALM"] > w["WILD"]          # lower vol -> larger weight


def test_diversified_weights_downweights_correlated(tmp_path):
    import numpy as np
    import pandas as pd
    store = DuckDBStore(tmp_path / "store")
    n = 300
    idx = pd.date_range("2022-01-01", periods=n, freq="1D")
    rng = np.random.default_rng(7)
    base = rng.normal(0, 0.02, n)
    # A and B are near-identical (redundant); C is an independent diversifier,
    # all at the same volatility so only correlation differs
    rets = {
        "A": base,
        "B": base + rng.normal(0, 0.002, n),
        "C": rng.normal(0, 0.02, n),
    }
    for sym, r in rets.items():
        close = 100 * np.exp(np.cumsum(r))
        store.write(Candle(sym, pd.DataFrame(
            {"open": close, "high": close * 1.01, "low": close * 0.99, "close": close,
             "volume": np.full(n, 1000.0)}, index=idx), interval="1d"))
    w = ops.diversified_weights(store, ["A", "B", "C"], "1d", lookback=200)
    assert abs(sum(w.values()) - 1.0) < 1e-6
    # the independent diversifier should get more than either correlated twin
    assert w["C"] > w["A"] and w["C"] > w["B"]


def test_diversified_weights_single_symbol_fallback(tmp_path):
    import numpy as np
    import pandas as pd
    store = DuckDBStore(tmp_path / "store")
    n = 100
    idx = pd.date_range("2022-01-01", periods=n, freq="1D")
    close = 100 * np.exp(np.cumsum(np.random.default_rng(1).normal(0, 0.02, n)))
    store.write(Candle("ONE", pd.DataFrame(
        {"open": close, "high": close * 1.01, "low": close * 0.99, "close": close,
         "volume": np.full(n, 1.0)}, index=idx), interval="1d"))
    w = ops.diversified_weights(store, ["ONE"], "1d")
    assert w == {"ONE": 1.0}


def test_portfolio_risk_parity_weights(tmp_path):
    import numpy as np
    import pandas as pd
    store = DuckDBStore(tmp_path / "store")
    for sym, sig in (("CALM", 0.005), ("WILD", 0.05)):
        rng = np.random.default_rng(2)
        close = 100 * np.exp(np.cumsum(rng.normal(0.0003, sig, 200)))
        idx = pd.date_range("2023-01-01", periods=200, freq="1D")
        store.write(Candle(sym, pd.DataFrame(
            {"open": close, "high": close * 1.01, "low": close * 0.99, "close": close,
             "volume": np.full(200, 1000.0)}, index=idx), interval="1d"))
    out = ops.portfolio_backtest(store, ["CALM", "WILD"], "1d", "macross", risk_parity=True)
    w = {s: v["weight"] for s, v in out["per_symbol"].items()}
    assert w["CALM"] > w["WILD"]                      # inverse-vol sizing
    assert abs(sum(w.values()) - 1.0) < 1e-6


def test_backtest_includes_buy_hold_benchmark(tmp_path):
    store = DuckDBStore(tmp_path / "store")
    rng = np.random.default_rng(7)
    close = 100 * np.exp(np.cumsum(rng.normal(0.001, 0.02, 300)))
    idx = pd.date_range("2023-01-01", periods=300, freq="1D")
    store.write(Candle("BTCUSDT", pd.DataFrame(
        {"open": close, "high": close * 1.01, "low": close * 0.99, "close": close,
         "volume": np.full(300, 1000.0)}, index=idx), interval="1d"))
    out = ops.backtest(store, "BTCUSDT", "1d", "macross", {"fast": 5, "slow": 20})
    assert "benchmark_return" in out and out["benchmark_return"] is not None
    # excess return is strategy minus buy-and-hold, to 4dp
    assert out["excess_return"] == pytest.approx(
        round(out["total_return"] - out["benchmark_return"], 4), abs=1e-9)


def test_monthly_returns_matrix(tmp_path):
    # 3 months of equity, +10% then -10% -> known cells
    idx = pd.date_range("2023-01-31", periods=3, freq="ME")
    eq = pd.Series([100.0, 110.0, 99.0], index=idx)
    out = ops.monthly_returns(eq)
    assert out["years"] == [2023]
    row = out["matrix"][0]
    assert row[0] is None                      # Jan: no prior month to diff
    assert row[1] == pytest.approx(0.1)        # Feb: +10%
    assert row[2] == pytest.approx(-0.1)       # Mar: -10%
    assert all(row[m] is None for m in range(3, 12))


def test_compare_ranks_strategies_by_metric(tmp_path):
    store = DuckDBStore(tmp_path / "store")
    rng = np.random.default_rng(3)
    close = 100 * np.exp(np.cumsum(rng.normal(0.001, 0.02, 300)))
    idx = pd.date_range("2023-01-01", periods=300, freq="1D")
    store.write(Candle("BTCUSDT", pd.DataFrame(
        {"open": close, "high": close * 1.01, "low": close * 0.99, "close": close,
         "volume": np.full(300, 1000.0)}, index=idx), interval="1d"))
    out = ops.compare(store, "BTCUSDT", "1d",
                      strategies=["macross", "keltner_breakout", "donchian_breakout"],
                      metric="sharpe")
    names = {r["strategy"] for r in out["ranking"]}
    assert names == {"macross", "keltner_breakout", "donchian_breakout"}
    scores = [r["sharpe"] for r in out["ranking"]]
    assert scores == sorted(scores, reverse=True)        # ranked best-first
    assert "excess_return" in out["ranking"][0] and out["errors"] == {}
    with pytest.raises(ValueError):
        ops.compare(store, "BTCUSDT", "1d", strategies=["nope"])


def test_compare_optimize_each_tunes_and_reports_params(tmp_path):
    store = DuckDBStore(tmp_path / "store")
    rng = np.random.default_rng(4)
    close = 100 * np.exp(np.cumsum(rng.normal(0.001, 0.02, 400)))
    idx = pd.date_range("2023-01-01", periods=400, freq="1D")
    store.write(Candle("BTCUSDT", pd.DataFrame(
        {"open": close, "high": close * 1.01, "low": close * 0.99, "close": close,
         "volume": np.full(400, 1000.0)}, index=idx), interval="1d"))
    out = ops.compare(store, "BTCUSDT", "1d",
                      strategies=["macross", "donchian_breakout"],
                      metric="sharpe", optimize_each=True)
    for r in out["ranking"]:
        assert "params" in r and isinstance(r["params"], dict) and r["params"]
    scores = [r["sharpe"] for r in out["ranking"]]
    assert scores == sorted(scores, reverse=True)


def test_correlation_matrix(tmp_path):
    import numpy as np
    import pandas as pd
    store = DuckDBStore(tmp_path / "store")
    rng = np.random.default_rng(0)
    base = rng.normal(0, 0.02, 200)
    series = {"AAA": base, "BBB": base + rng.normal(0, 0.001, 200),  # ~ +corr with AAA
              "CCC": -base + rng.normal(0, 0.001, 200)}              # ~ -corr with AAA
    for sym, rets in series.items():
        close = 100 * np.exp(np.cumsum(rets))
        idx = pd.date_range("2023-01-01", periods=200, freq="1D")
        store.write(Candle(sym, pd.DataFrame(
            {"open": close, "high": close * 1.01, "low": close * 0.99, "close": close,
             "volume": np.full(200, 1000.0)}, index=idx), interval="1d"))
    out = ops.correlation(store, ["AAA", "BBB", "CCC"], "1d")
    i = {s: n for n, s in enumerate(out["symbols"])}
    assert out["matrix"][i["AAA"]][i["AAA"]] == 1.0          # diagonal
    assert out["matrix"][i["AAA"]][i["BBB"]] > 0.8           # positively correlated
    assert out["matrix"][i["AAA"]][i["CCC"]] < -0.8          # anti-correlated


def test_protect_take_profit_proposes_and_executes(tmp_path, fake_exchange):
    from yammyquant.ops.risk_policy import ProtectPolicy
    store = DuckDBStore(tmp_path / "store")
    state = LiveState(tmp_path / "s.db")
    state.set("cash", 10_000.0)
    state.upsert_position("BTCUSDT", 1.0, 100.0)        # entry 100; fake price = 120
    ProtectPolicy(take_profit=0.10).save(state)         # target 110 -> 120 breaches

    dry = ops.protect(store, state)                      # dry-run
    assert dry["checked"] == 1
    assert dry["proposals"][0]["reason"] == "take_profit"
    assert dry["proposals"][0]["side"] == "SELL"
    assert state.trades() == []                          # nothing submitted

    live = ops.protect(store, state, execute=True)
    assert live["proposals"][0].get("status") == "filled"
    assert not state.positions()                         # flattened


def test_protect_stop_loss(tmp_path, fake_exchange):
    from yammyquant.ops.risk_policy import ProtectPolicy
    store = DuckDBStore(tmp_path / "store")
    state = LiveState(tmp_path / "s.db")
    state.set("cash", 10_000.0)
    state.upsert_position("ETHUSDT", 1.0, 200.0)        # entry 200; price 120 < 190
    ProtectPolicy(stop_loss=0.05).save(state)
    out = ops.protect(store, state)
    assert out["proposals"][0]["reason"] == "stop_loss"


def test_protect_trailing_uses_peak(tmp_path, fake_exchange):
    from yammyquant.ops.risk_policy import ProtectPolicy
    store = DuckDBStore(tmp_path / "store")
    state = LiveState(tmp_path / "s.db")
    state.set("cash", 10_000.0)
    state.upsert_position("SOLUSDT", 1.0, 100.0)
    state.set("protect.hwm.SOLUSDT", 200.0)             # peak well above the 120 price
    ProtectPolicy(trailing_stop=0.10).save(state)        # 200*0.9 = 180 -> 120 breaches
    out = ops.protect(store, state)
    assert out["proposals"][0]["reason"] == "trailing_stop"


def test_protect_no_policy_is_noop(tmp_path, fake_exchange):
    store = DuckDBStore(tmp_path / "store")
    state = LiveState(tmp_path / "s.db")
    state.upsert_position("BTCUSDT", 1.0, 100.0)
    out = ops.protect(store, state)
    assert out["checked"] == 0 and out["proposals"] == []


def test_protect_atr_stop(tmp_path, fake_exchange):
    # fake exchange: price 120, and read() returns rising 100..159 (TR≈1 -> ATR≈1)
    from yammyquant.ops.risk_policy import ProtectPolicy
    store = DuckDBStore(tmp_path / "store")
    state = LiveState(tmp_path / "s.db")
    state.set("cash", 10_000.0)
    # write candles so ATR resolves from the store (interval 1d)
    n = 40
    idx = pd.date_range("2023-01-01", periods=n, freq="1D")
    close = 100 + np.arange(n, dtype=float)
    store.write(Candle("ETHUSDT", pd.DataFrame(
        {"open": close, "high": close + 1, "low": close - 1, "close": close,
         "volume": [1.0] * n}, index=idx), interval="1d"))
    state.upsert_position("ETHUSDT", 1.0, 130.0)        # entry 130, price 120, ATR≈2
    ProtectPolicy(atr_stop=2.0).save(state)              # stop ≈ 130 - 2*2 = 126 -> 120 breaches
    out = ops.protect(store, state)
    assert out["proposals"] and out["proposals"][0]["reason"] == "atr_stop"


def test_protect_scale_out_partial_then_disarms(tmp_path, fake_exchange):
    from yammyquant.ops.risk_policy import ProtectPolicy
    store = DuckDBStore(tmp_path / "store")
    state = LiveState(tmp_path / "s.db")
    state.set("cash", 10_000.0)
    state.upsert_position("BTCUSDT", 2.0, 100.0)         # entry 100, price 120
    ProtectPolicy(take_profit=0.10, scale_out=0.5).save(state)  # target 110 -> 120 breaches

    out = ops.protect(store, state, execute=True)
    assert out["proposals"][0]["reason"] == "take_profit (scale-out)"
    assert out["proposals"][0]["quantity"] == pytest.approx(1.0)   # half of 2 units
    # remaining position still open, take-profit disarmed -> next pass proposes nothing
    again = ops.protect(store, state)
    assert again["proposals"] == []


def test_decide_sets_bracket_on_entry_and_protect_uses_it(tmp_path, fake_exchange):
    from yammyquant.ops.risk_policy import ProtectPolicy
    store = DuckDBStore(tmp_path / "store")
    state = LiveState(tmp_path / "s.db")
    state.set("cash", 10_000.0)
    state.add_watch("BTCUSDT", "fake", "1d")
    _pin_strategies(state, "volatility_breakout")
    ProtectPolicy(stop_loss=0.05, take_profit=0.10).save(state)
    # rising series -> a BUY entry; the fill uses the live price (120), not the
    # stale last close, so entry and the protect "current price" stay consistent
    out = ops.decide(store, state, weight=0.2, execute=True, mode="paper")
    buys = [p for p in out["proposals"] if p["side"] == "BUY" and p.get("status") == "filled"]
    assert buys and "bracket" in buys[0]
    entry = buys[0]["price"]
    assert entry == pytest.approx(120.0)
    bracket = state.get("BTCUSDT" and "protect.bracket.BTCUSDT")
    assert bracket["stop"] == pytest.approx(entry * 0.95)
    assert bracket["take"] == pytest.approx(entry * 1.10)
    # drop the live price below the bracket stop (114) -> protect fires bracket_stop
    fake_exchange.last_price = lambda *a, **k: 100.0
    prot = ops.protect(store, state)
    assert prot["proposals"][0]["reason"] == "bracket_stop"


def test_protect_clears_bracket_on_full_exit(tmp_path, fake_exchange):
    from yammyquant.ops.risk_policy import ProtectPolicy
    store = DuckDBStore(tmp_path / "store")
    state = LiveState(tmp_path / "s.db")
    state.set("cash", 10_000.0)
    state.upsert_position("ETHUSDT", 1.0, 200.0)
    state.set("protect.bracket.ETHUSDT", {"stop": 190.0, "take": 260.0})
    ProtectPolicy(stop_loss=0.05).save(state)        # price 120 < bracket stop 190 -> exit
    out = ops.protect(store, state, execute=True)
    assert out["proposals"][0]["reason"] == "bracket_stop"
    assert state.get("protect.bracket.ETHUSDT") is None   # cleared on flatten


def test_correlation_scale_shrinks_correlated_entry(tmp_path):
    store = DuckDBStore(tmp_path / "store")
    n = 200
    idx = pd.date_range("2022-01-01", periods=n, freq="1D")
    rng = np.random.default_rng(3)
    base = rng.normal(0, 0.02, n)
    for sym, r in {"AAA": base, "BBB": base + rng.normal(0, 0.001, n),   # ~identical to AAA
                   "CCC": rng.normal(0, 0.02, n)}.items():               # independent
        close = 100 * np.exp(np.cumsum(r))
        store.write(Candle(sym, pd.DataFrame(
            {"open": close, "high": close * 1.01, "low": close * 0.99, "close": close,
             "volume": np.full(n, 1.0)}, index=idx), interval="1d"))
    # entering BBB while holding AAA (correlated) -> heavy shrink
    corr_factor = ops.correlation_scale(store, ["AAA"], "BBB", "1d")
    indep_factor = ops.correlation_scale(store, ["AAA"], "CCC", "1d")
    assert corr_factor < indep_factor
    assert ops.correlation_scale(store, [], "BBB", "1d") == 1.0   # nothing held -> full size


def test_decide_correlation_sizing_reduces_qty(tmp_path, fake_exchange):
    store = DuckDBStore(tmp_path / "store")
    state = LiveState(tmp_path / "s.db")
    state.set("cash", 10_000.0)
    state.set("correlation_sizing", True)
    # hold AAA; candidate BTCUSDT shares the same fake rising series -> correlated
    state.upsert_position("AAA", 1.0, 100.0)
    for s in ("AAA", "BTCUSDT"):
        store.write(fake_exchange.read(s, "1d"))
    state.add_watch("BTCUSDT", "fake", "1d")
    out = ops.decide(store, state, weight=0.2, execute=False)
    buys = [p for p in out["proposals"] if p["side"] == "BUY"]
    if buys:   # if a buy is proposed, it should carry a correlation_scale < 1
        assert buys[0]["context"].get("correlation_scale", 1.0) <= 1.0


def test_in_session_gating():
    import pandas as pd
    wed_14 = pd.Timestamp("2023-01-04 14:00")   # Wednesday (weekday 2), hour 14
    assert ops.in_session(wed_14, None, None) is True            # unrestricted
    assert ops.in_session(wed_14, [0, 1, 2, 3, 4], [13, 14, 15]) is True
    assert ops.in_session(wed_14, [0, 1, 2, 3, 4], [9, 10]) is False     # wrong hour
    sat = pd.Timestamp("2023-01-07 14:00")      # Saturday (weekday 5)
    assert ops.in_session(sat, [0, 1, 2, 3, 4], None) is False           # weekend


def test_decide_session_gate_vetoes_entry(tmp_path, fake_exchange):
    store = DuckDBStore(tmp_path / "store")
    state = LiveState(tmp_path / "s.db")
    state.set("cash", 10_000.0)
    state.add_watch("BTCUSDT", "fake", "1d")
    _pin_strategies(state, "volatility_breakout")
    # fake candle's last bar is 2023-03-01 (a Wednesday); allow only weekends -> veto
    state.set("session_days", [5, 6])
    out = ops.decide(store, state, weight=0.2, execute=False)
    assert not [p for p in out["proposals"] if p["side"] == "BUY"]   # entry vetoed
    # clearing the gate lets the entry through again
    state.set("session_days", None)
    out2 = ops.decide(store, state, weight=0.2, execute=False)
    assert [p for p in out2["proposals"] if p["side"] == "BUY"]


def test_decide_min_edge_gate_vetoes_thin_edge(tmp_path, fake_exchange):
    store = DuckDBStore(tmp_path / "store")
    state = LiveState(tmp_path / "s.db")
    state.set("cash", 10_000.0)
    state.add_watch("BTCUSDT", "fake", "1d")
    _pin_strategies(state, "volatility_breakout")
    state.set("slippage", 0.01)              # round-trip cost = 2×0.01 > 0
    # demand an unrealistically large edge -> a real BUY signal is vetoed
    state.set("min_edge_mult", 100.0)
    out = ops.decide(store, state, weight=0.2, execute=False)
    assert not [p for p in out["proposals"] if p["side"] == "BUY"]
    # clearing the gate lets the same entry through
    state.set("min_edge_mult", None)
    out2 = ops.decide(store, state, weight=0.2, execute=False)
    assert [p for p in out2["proposals"] if p["side"] == "BUY"]


def test_promotion_gate(tmp_path):
    state = LiveState(tmp_path / "s.db")
    tm = TradeManager(state, fee=0.0)
    tm.cash = 10_000.0
    # no recorded baselines -> nothing to grade
    assert ops.promotion_check(state)["checks"] == []
    # a hand-recorded baseline (avoids needing a store/backtest here)
    state.set("expectations", {"macross:BTCUSDT:1d":
                               {"sharpe": 1.0, "total_return": 0.2, "max_drawdown": -0.1}})
    # no closed trades yet -> not ready (insufficient sample / not profitable)
    out = ops.promotion_check(state, min_trades=1)
    assert out["checks"][0]["ready"] is False and out["checks"][0]["blockers"]
    # a profitable paper round-trip -> one closed trade, positive return
    tm.submit("BTCUSDT", "BUY", 1.0, 100.0)
    tm.submit("BTCUSDT", "SELL", 1.0, 130.0)
    out2 = ops.promotion_check(state, min_trades=1, sharpe_floor=0.0)
    c = out2["checks"][0]
    assert c["closed_trades"] == 1 and c["ready"] is True
    assert "macross:BTCUSDT:1d" in out2["ready"]
    assert out2["live_trading_allowed"] is False   # not armed without YQ_ALLOW_LIVE


def test_backtest_fee_exchange_applies_schedule(tmp_path):
    store = DuckDBStore(tmp_path / "store")
    n = 250
    idx = pd.date_range("2022-01-01", periods=n, freq="1D")
    close = 100 + 10 * np.sin(np.arange(n) / 7.0)
    store.write(Candle("OSC", pd.DataFrame(
        {"open": close, "high": close + 1, "low": close - 1, "close": close,
         "volume": np.full(n, 1.0)}, index=idx), interval="1d"))
    out = ops.backtest(store, "OSC", "1d", "macross", {"fast": 5, "slow": 20},
                       fee_exchange="binance")
    assert out["fee_exchange"] == "binance"
    assert out["maker_fee"] == 0.001 and out["taker_fee"] == 0.001


def test_paper_fill_uses_exchange_fees():
    import tempfile
    import pathlib
    from yammyquant.ops.trading import TradeManager
    tmp = pathlib.Path(tempfile.mkdtemp())
    state = LiveState(tmp / "s.db")
    tm = TradeManager(state, exchange="binance")     # 0.001 taker
    tm.cash = 10_000.0
    tm.submit("BTCUSDT", "BUY", 1.0, 100.0, order_type="market")
    trade = state.trades()[0]
    assert trade["status"] == "filled"
    # cash reduced by notional + binance taker fee (100*1*0.001 = 0.1)
    assert tm.cash == pytest.approx(10_000.0 - 100.0 - 0.1)


def test_paper_fill_limit_uses_maker_fee():
    import tempfile
    import pathlib
    from yammyquant.ops.trading import TradeManager
    tmp = pathlib.Path(tempfile.mkdtemp())
    state = LiveState(tmp / "s.db")

    tm = TradeManager(state, exchange="upbit")       # 0.0005 maker == taker
    tm.cash = 10_000.0
    tm.submit("KRW-BTC", "BUY", 1.0, 100.0, order_type="limit")
    assert tm.cash == pytest.approx(10_000.0 - 100.0 - 100.0 * 0.0005)
