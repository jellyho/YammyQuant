import numpy as np
import pandas as pd
import pytest

from yammyquant.data.candle import Candle


@pytest.fixture
def sine_candle() -> Candle:
    """A deterministic oscillating price series, good for crossover tests."""
    n = 300
    idx = pd.date_range("2023-01-01", periods=n, freq="1D")
    t = np.arange(n)
    close = 100 + 10 * np.sin(t / 8.0)
    df = pd.DataFrame(
        {
            "open": close,
            "high": close + 1.0,
            "low": close - 1.0,
            "close": close,
            "volume": np.full(n, 1000.0),
        },
        index=idx,
    )
    return Candle("TESTUSDT", df, interval="1d")


@pytest.fixture
def trend_candle() -> Candle:
    """A steadily rising series."""
    n = 100
    idx = pd.date_range("2023-01-01", periods=n, freq="1D")
    close = np.linspace(100, 200, n)
    df = pd.DataFrame(
        {
            "open": close,
            "high": close + 0.5,
            "low": close - 0.5,
            "close": close,
            "volume": np.full(n, 500.0),
        },
        index=idx,
    )
    return Candle("UPUSDT", df, interval="1d")


class _FakeExchange:
    """Rising-series exchange for operator/ensemble tests (shared fixture)."""

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
    fake = _FakeExchange()
    monkeypatch.setattr("yammyquant.exchanges.get_exchange", lambda name=None, **k: fake)
    monkeypatch.setattr("yammyquant.exchanges.default_exchange", lambda: "fake")
    return fake
