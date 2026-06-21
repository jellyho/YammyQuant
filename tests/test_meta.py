import numpy as np
import pandas as pd

from yammyquant.data.candle import Candle
from yammyquant.backtest.order import Action, Order
from yammyquant.strategy.base import Strategy
from yammyquant.strategy.meta import RegimeFilter, SessionFilter


class _AlwaysBuy(Strategy):
    warmup = 1

    def on_bar(self, window):
        return [Order(Action.BUY, window.ticker, 1.0, float(window.close[-1]))]


def _window(closes):
    idx = pd.date_range("2023-01-01", periods=len(closes), freq="1D")
    c = np.array(closes, dtype=float)
    df = pd.DataFrame({"open": c, "high": c + 1, "low": c - 1, "close": c,
                       "volume": np.full(len(c), 1.0)}, index=idx)
    return Candle("X", df, interval="1d")


def test_regime_blocks_buy_below_trend():
    # downtrend: last close below the 10-bar average -> long entry suppressed
    win = _window(list(np.linspace(120, 100, 12)))
    rf = RegimeFilter(_AlwaysBuy(), trend_period=10)
    assert rf.on_bar(win) == []


def test_regime_allows_buy_above_trend():
    # uptrend: last close above the average -> entry passes through
    win = _window(list(np.linspace(100, 120, 12)))
    rf = RegimeFilter(_AlwaysBuy(), trend_period=10)
    orders = rf.on_bar(win)
    assert len(orders) == 1 and orders[0].action == Action.BUY


def test_regime_always_lets_sells_through():
    class _AlwaysSell(Strategy):
        warmup = 1
        def on_bar(self, window):
            return [Order(Action.SELL, window.ticker, 1.0, float(window.close[-1]))]

    win = _window(list(np.linspace(120, 100, 12)))   # downtrend
    rf = RegimeFilter(_AlwaysSell(), trend_period=10)
    orders = rf.on_bar(win)
    assert len(orders) == 1 and orders[0].action == Action.SELL   # exits never blocked


def test_regime_warmup_accounts_for_htf():
    rf = RegimeFilter(_AlwaysBuy(), trend_period=50, htf_factor=7)
    assert rf.warmup == 350


def test_regime_backtest_reduces_trades(tmp_path):
    from yammyquant.data.sources.store import DuckDBStore
    from yammyquant.ops import operator as ops

    store = DuckDBStore(tmp_path / "store")
    # choppy series so an unfiltered MA cross trades a lot
    n = 300
    idx = pd.date_range("2022-01-01", periods=n, freq="1D")
    close = 100 + 8 * np.sin(np.arange(n) / 6.0)
    store.write(Candle("CHOP", pd.DataFrame(
        {"open": close, "high": close + 1, "low": close - 1, "close": close,
         "volume": np.full(n, 1.0)}, index=idx), interval="1d"))
    base = ops.backtest(store, "CHOP", "1d", "macross", {"fast": 5, "slow": 20})
    filt = ops.backtest(store, "CHOP", "1d", "macross", {"fast": 5, "slow": 20},
                        regime={"trend_period": 50})
    # the trend gate should not increase trade count (typically reduces it)
    assert filt["num_trades"] <= base["num_trades"]


class _AlwaysSellStrat(Strategy):
    warmup = 1
    def on_bar(self, window):
        return [Order(Action.SELL, window.ticker, 1.0, float(window.close[-1]))]


def _hourly_window(end_hour):
    # 3 hourly bars ending at a chosen hour on a Wednesday (weekday 2)
    idx = pd.date_range(f"2023-01-04 {end_hour-2:02d}:00", periods=3, freq="1h")
    c = np.array([100.0, 101, 102])
    df = pd.DataFrame({"open": c, "high": c + 1, "low": c - 1, "close": c,
                       "volume": [1.0] * 3}, index=idx)
    return Candle("X", df, interval="1h")


def test_session_blocks_buy_outside_hours():
    win = _hourly_window(end_hour=3)                  # 03:00, outside 13–16
    sf = SessionFilter(_AlwaysBuy(), hours=[13, 14, 15, 16])
    assert sf.on_bar(win) == []


def test_session_allows_buy_inside_hours():
    win = _hourly_window(end_hour=14)                 # 14:00, inside
    sf = SessionFilter(_AlwaysBuy(), hours=[13, 14, 15, 16])
    orders = sf.on_bar(win)
    assert len(orders) == 1 and orders[0].action == Action.BUY


def test_session_blocks_weekend_entry():
    # Saturday is weekday 5; only allow Mon–Fri (0–4)
    idx = pd.date_range("2023-01-07", periods=2, freq="1D")   # 2023-01-07 is a Saturday
    c = np.array([100.0, 101])
    df = pd.DataFrame({"open": c, "high": c + 1, "low": c - 1, "close": c,
                       "volume": [1.0, 1.0]}, index=idx)
    sf = SessionFilter(_AlwaysBuy(), weekdays=[0, 1, 2, 3, 4])
    assert sf.on_bar(Candle("X", df, interval="1d")) == []


def test_session_always_allows_exits():
    win = _hourly_window(end_hour=3)                  # out of session
    sf = SessionFilter(_AlwaysSellStrat(), hours=[13, 14])
    orders = sf.on_bar(win)
    assert len(orders) == 1 and orders[0].action == Action.SELL
