import numpy as np
import pandas as pd

from yammyquant.data.candle import Candle
from yammyquant.data.integrity import candle_integrity


def _candle(df):
    return Candle("X", df, interval="1d")


def test_clean_series_is_ok():
    idx = pd.date_range("2023-01-01", periods=10, freq="1D")
    close = np.linspace(100, 110, 10)
    df = pd.DataFrame({"open": close, "high": close + 1, "low": close - 1,
                       "close": close, "volume": np.full(10, 5.0)}, index=idx)
    rep = candle_integrity(_candle(df), interval_seconds=86400)
    assert rep["ok"] and rep["bars"] == 10
    assert rep["gaps"] == 0 and rep["duplicates"] == 0


def test_detects_gap():
    # drop two days -> one gap of ~3 days, ~2 missing bars
    idx = pd.to_datetime(["2023-01-01", "2023-01-02", "2023-01-05", "2023-01-06"])
    c = np.array([100.0, 101, 102, 103])
    df = pd.DataFrame({"open": c, "high": c + 1, "low": c - 1, "close": c,
                       "volume": [1.0] * 4}, index=idx)
    rep = candle_integrity(_candle(df), interval_seconds=86400)
    assert rep["gaps"] == 1
    assert rep["missing_estimate"] == 2
    assert not rep["ok"]


def test_detects_duplicate_and_disorder():
    idx = pd.to_datetime(["2023-01-01", "2023-01-01", "2023-01-03"])  # dup
    c = np.array([100.0, 100, 101])
    df = pd.DataFrame({"open": c, "high": c + 1, "low": c - 1, "close": c,
                       "volume": [1.0] * 3}, index=idx)
    rep = candle_integrity(_candle(df), interval_seconds=86400)
    assert rep["duplicates"] == 1
    assert rep["out_of_order"] >= 1


def test_detects_bad_ohlc_and_nonpositive():
    idx = pd.date_range("2023-01-01", periods=3, freq="1D")
    # row 1: high < low (impossible); row 2: nonpositive price
    df = pd.DataFrame(
        {"open": [100.0, 100.0, 100.0],
         "high": [101.0, 95.0, 101.0],     # bar1 high 95 < low 99 -> bad
         "low":  [99.0, 99.0, 99.0],
         "close": [100.0, 100.0, -5.0],    # bar2 negative close
         "volume": [1.0, 1.0, 1.0]},
        index=idx,
    )
    rep = candle_integrity(_candle(df), interval_seconds=86400)
    assert rep["bad_ohlc"] >= 1
    assert rep["nonpositive"] >= 1
    assert not rep["ok"]


def test_empty_series_is_safe():
    df = pd.DataFrame({"open": [], "high": [], "low": [], "close": [], "volume": []},
                      index=pd.to_datetime([]))
    rep = candle_integrity(_candle(df))
    assert rep["bars"] == 0 and rep["ok"]


def test_operator_integrity_scans_store(tmp_path):
    from yammyquant.data.sources.store import DuckDBStore
    from yammyquant.ops import operator as ops

    store = DuckDBStore(tmp_path / "store")
    idx = pd.date_range("2023-01-01", periods=8, freq="1D")
    close = np.linspace(100, 108, 8)
    store.write(Candle("AAA", pd.DataFrame(
        {"open": close, "high": close + 1, "low": close - 1, "close": close,
         "volume": np.full(8, 3.0)}, index=idx), interval="1d"))
    out = ops.integrity(store, "AAA", "1d")
    assert out["ok"] and out["series"][0]["bars"] == 8


def test_resample_hourly_to_4h():
    from yammyquant.data.resample import resample_candle
    # 8 hourly bars -> two 4h bars; check OHLCV aggregation
    idx = pd.date_range("2023-01-01 00:00", periods=8, freq="1h")
    df = pd.DataFrame({
        "open":  [10, 11, 12, 13, 20, 21, 22, 23],
        "high":  [15, 16, 17, 18, 25, 26, 27, 28],
        "low":   [5, 6, 7, 8, 15, 16, 17, 18],
        "close": [11, 12, 13, 14, 21, 22, 23, 24],
        "volume": [1, 1, 1, 1, 2, 2, 2, 2],
    }, index=idx, dtype=float)
    out = resample_candle(Candle("X", df, interval="1h"), "4h")
    assert len(out) == 2
    assert list(out.open) == [10.0, 20.0]        # first
    assert list(out.high) == [18.0, 28.0]        # max
    assert list(out.low) == [5.0, 15.0]          # min
    assert list(out.close) == [14.0, 24.0]       # last
    assert list(out.volume) == [4.0, 8.0]        # sum


def test_resample_rejects_finer_target():
    import pytest
    from yammyquant.data.resample import resample_candle
    idx = pd.date_range("2023-01-01", periods=4, freq="1D")
    c = np.array([100.0, 101, 102, 103])
    df = pd.DataFrame({"open": c, "high": c + 1, "low": c - 1, "close": c,
                       "volume": [1.0] * 4}, index=idx)
    with pytest.raises(ValueError, match="finer"):
        resample_candle(Candle("X", df, interval="1d"), "1h")


def test_operator_resample_writes(tmp_path):
    from yammyquant.data.sources.store import DuckDBStore
    from yammyquant.ops import operator as ops
    store = DuckDBStore(tmp_path / "store")
    idx = pd.date_range("2023-01-01", periods=48, freq="1h")
    close = 100 + np.arange(48, dtype=float)
    store.write(Candle("BTCUSDT", pd.DataFrame(
        {"open": close, "high": close + 1, "low": close - 1, "close": close,
         "volume": [1.0] * 48}, index=idx), interval="1h"))
    out = ops.resample(store, "BTCUSDT", "1h", "1d")
    assert out["target_bars"] == 2 and out["written"]
    assert len(store.read("BTCUSDT", "1d")) == 2
