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
