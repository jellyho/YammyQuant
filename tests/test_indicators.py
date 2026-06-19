import numpy as np

from yammyquant.data.indicators import REGISTRY


def test_sma_matches_manual(sine_candle):
    sma = sine_candle.ind.sma(5)
    manual = np.convolve(sine_candle.close, np.ones(5) / 5, mode="valid")
    np.testing.assert_allclose(sma.dropna().to_numpy()[: len(manual)], manual, rtol=1e-9)


def test_rsi_bounded(sine_candle):
    rsi = sine_candle.ind.rsi(14).dropna()
    assert (rsi >= 0).all() and (rsi <= 100).all()


def test_registry_indicators_run(sine_candle):
    # every registered indicator should execute without error
    for name in REGISTRY:
        result = getattr(sine_candle.ind, name)()
        assert len(result) == len(sine_candle)


def test_bbands_ordering(sine_candle):
    bb = sine_candle.ind.bbands(20).dropna()
    assert (bb["upper"] >= bb["middle"]).all()
    assert (bb["middle"] >= bb["lower"]).all()
