"""Position sizing methods."""

import numpy as np
import pandas as pd

from yammyquant.data.candle import Candle
from yammyquant.ops.sizing import position_size, kelly_fraction


def _candle(vol=0.01, n=120):
    rng = np.random.default_rng(0)
    rets = rng.normal(0, vol, n)
    close = 100 * np.exp(np.cumsum(rets))
    idx = pd.date_range("2023-01-01", periods=n, freq="1D")
    df = pd.DataFrame({"open": close, "high": close * 1.01, "low": close * 0.99,
                       "close": close, "volume": np.full(n, 1000.0)}, index=idx)
    return Candle("T", df, interval="1d")


def test_fixed_sizing():
    qty = position_size("fixed", equity=10_000, price=100, weight=0.1)
    assert qty == 10.0          # 10% of 10k / 100


def test_volatility_sizing_derisks_in_high_vol():
    calm = position_size("volatility", 10_000, 100, 0.1, candle=_candle(vol=0.005),
                         target_vol=0.5)
    wild = position_size("volatility", 10_000, 100, 0.1, candle=_candle(vol=0.05),
                         target_vol=0.5)
    # never exceeds the fixed size, and a wilder series gets a smaller position
    assert calm <= 10.0 and wild < calm


def test_kelly_fraction_and_sizing():
    # 3 wins of +100, 1 loss of -50 → positive edge → positive fraction
    trades = [{"status": "filled", "realized_pnl": x} for x in (100, 100, 100, -50)]
    f = kelly_fraction(trades)
    assert 0 < f <= 0.25
    qty = position_size("kelly", 10_000, 100, 0.1, trades=trades)
    assert qty > 0
    # no losers → no Kelly estimate → 0
    assert kelly_fraction([{"status": "filled", "realized_pnl": 10}]) == 0.0


def test_sizing_guards():
    assert position_size("fixed", 0, 100, 0.1) == 0.0
    assert position_size("fixed", 10_000, 0, 0.1) == 0.0
    assert position_size("kelly", 10_000, 100, 0.1, trades=[]) == 0.0
