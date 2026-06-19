"""Runnable backtest example using synthetic data (no network/DB needed).

    python examples/backtest_synthetic.py
"""

import numpy as np
import pandas as pd

from yammyquant import Backtest, Candle, MACross


def make_candle(n: int = 500) -> Candle:
    idx = pd.date_range("2022-01-01", periods=n, freq="1D")
    t = np.arange(n)
    # trend + cycle + noise
    close = 100 + t * 0.1 + 15 * np.sin(t / 20.0) + np.random.default_rng(0).normal(0, 1, n)
    df = pd.DataFrame(
        {
            "open": close,
            "high": close + 1,
            "low": close - 1,
            "close": close,
            "volume": np.full(n, 1000.0),
        },
        index=idx,
    )
    return Candle("DEMOUSDT", df, interval="1d")


def main():
    candle = make_candle()
    result = Backtest(candle, MACross(fast=10, slow=30, size=1.0), cash=10_000, fee=0.001).run()
    print(result)
    print("\nlast 5 trades:")
    print(result.trades.tail())


if __name__ == "__main__":
    main()
