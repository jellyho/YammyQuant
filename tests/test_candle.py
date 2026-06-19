import numpy as np
import pandas as pd
import pytest

from yammyquant.data.candle import Candle


def test_requires_ohlcv_columns():
    df = pd.DataFrame({"open": [1.0], "close": [1.0]})
    with pytest.raises(ValueError, match="missing required OHLCV"):
        Candle("X", df)


def test_column_accessors_return_arrays(sine_candle):
    assert isinstance(sine_candle.close, np.ndarray)
    assert len(sine_candle.close) == len(sine_candle)
    assert sine_candle.high[0] >= sine_candle.low[0]


def test_slice_returns_candle(sine_candle):
    sub = sine_candle[-50:]
    assert isinstance(sub, Candle)
    assert len(sub) == 50
    assert sub.ticker == sine_candle.ticker


def test_int_index_returns_single_bar_candle(sine_candle):
    bar = sine_candle[-1]
    assert isinstance(bar, Candle)
    assert len(bar) == 1


def test_unknown_indicator_raises_attribute_error(sine_candle):
    with pytest.raises(AttributeError, match="Unknown indicator"):
        sine_candle.ind.not_a_real_indicator()
