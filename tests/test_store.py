import pandas as pd
import pytest

from yammyquant.data.candle import Candle
from yammyquant.data.sources.store import DuckDBStore


def _make_candle(ticker="BTCUSDT", n=50):
    idx = pd.date_range("2023-01-01", periods=n, freq="1D")
    close = pd.Series(range(100, 100 + n), dtype=float)
    df = pd.DataFrame(
        {"open": close, "high": close + 1, "low": close - 1, "close": close, "volume": close},
        index=idx,
    )
    return Candle(ticker, df, interval="1d")


def test_write_read_roundtrip(tmp_path):
    store = DuckDBStore(tmp_path)
    store.write(_make_candle())
    out = store.read("BTCUSDT", "1d")
    assert len(out) == 50
    assert out.ticker == "BTCUSDT"


def test_date_range_filter(tmp_path):
    store = DuckDBStore(tmp_path)
    store.write(_make_candle())
    out = store.read("BTCUSDT", "1d", start="2023-01-10 00:00:00", end="2023-01-20 00:00:00")
    assert len(out) == 11


def test_upsert_dedupes(tmp_path):
    store = DuckDBStore(tmp_path)
    store.write(_make_candle(n=50))
    store.write(_make_candle(n=60))  # overlapping range
    out = store.read("BTCUSDT", "1d")
    assert len(out) == 60  # no duplicates


def test_info_and_last_time(tmp_path):
    store = DuckDBStore(tmp_path)
    store.write(_make_candle())
    assert store.info() == {"BTCUSDT": ["1d"]}
    assert store.last_time("BTCUSDT", "1d") is not None


def test_missing_file_raises(tmp_path):
    store = DuckDBStore(tmp_path)
    with pytest.raises(FileNotFoundError):
        store.read("NOPE", "1d")
