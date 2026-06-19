import pandas as pd
import pytest

from yammyquant.data.candle import Candle
from yammyquant.data.sources.store import DuckDBStore
from yammyquant.state.store import LiveState
from yammyquant.ops import operator as ops


def _seed_store(tmp_path):
    store = DuckDBStore(tmp_path / "store")
    n = 120
    idx = pd.date_range("2023-01-01", periods=n, freq="1D")
    import numpy as np
    close = 100 + 10 * np.sin(np.arange(n) / 8.0)
    df = pd.DataFrame(
        {"open": close, "high": close + 1, "low": close - 1, "close": close, "volume": [1000.0] * n},
        index=idx,
    )
    store.write(Candle("BTCUSDT", df, interval="1d"))
    return store


def test_backtest_records_activity(tmp_path):
    store = _seed_store(tmp_path)
    state = LiveState(tmp_path / "s.db")
    stats = ops.backtest(store, "BTCUSDT", "1d", "macross", {"fast": 5, "slow": 20}, state=state)
    assert "sharpe" in stats
    assert state.activity()[0]["kind"] == "backtest"


def test_scan_emits_signals(tmp_path):
    store = _seed_store(tmp_path)
    state = LiveState(tmp_path / "s.db")
    rows = ops.scan(store, ["BTCUSDT"], "1d", "macross", state=state)
    assert rows and rows[0]["ticker"] == "BTCUSDT"
    assert state.activity()[0]["kind"] == "scan"


def test_unknown_strategy_raises(tmp_path):
    store = _seed_store(tmp_path)
    with pytest.raises(ValueError, match="unknown strategy"):
        ops.backtest(store, "BTCUSDT", "1d", "nope")
