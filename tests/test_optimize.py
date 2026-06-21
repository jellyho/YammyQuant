import pytest

from yammyquant.backtest.optimize import grid_search, walk_forward
from yammyquant.strategy.builtin import MACross


def test_grid_search_ranks_and_skips_invalid(sine_candle):
    grid = {"fast": [5, 10, 50], "slow": [20, 30]}  # some combos invalid (fast>=slow)
    res = grid_search(sine_candle, MACross, grid, metric="sharpe")
    assert res.best_params["fast"] < res.best_params["slow"]
    # results sorted best-first
    scores = [r["score"] for r in res.results]
    assert scores == sorted(scores, reverse=True)


def test_grid_search_all_invalid_raises(sine_candle):
    with pytest.raises(ValueError, match="no valid"):
        grid_search(sine_candle, MACross, {"fast": [50], "slow": [20]})


def test_grid_search_reports_deflated_sharpe(sine_candle):
    grid = {"fast": [5, 10], "slow": [20, 30, 40]}
    res = grid_search(sine_candle, MACross, grid, metric="sharpe")
    assert res.dsr is not None
    assert 0.0 <= res.dsr <= 1.0


def test_grid_search_passes_backtest_kwargs(sine_candle):
    grid = {"fast": [5, 10], "slow": [20, 30]}
    # pass-through kwargs (allow_short, fill_timing, borrow_fee) must be accepted
    res = grid_search(sine_candle, MACross, grid, metric="sharpe",
                      allow_short=True, fill_timing="close", borrow_fee=0.05)
    assert res.best_params["fast"] < res.best_params["slow"]
    # 'close' fill timing should generally differ from the default 'next_open'
    res_default = grid_search(sine_candle, MACross, grid, metric="sharpe")
    assert isinstance(res_default.best_score, float)


def test_deflated_sharpe_metric_penalizes_many_trials():
    import numpy as np
    import pandas as pd
    from yammyquant.metrics.performance import (
        deflated_sharpe_ratio, probabilistic_sharpe_ratio)
    rng = np.random.default_rng(0)
    rets = pd.Series(rng.normal(0.001, 0.01, 400))
    psr = probabilistic_sharpe_ratio(rets)
    spread = list(rng.normal(0.5, 0.5, 50))            # 50 noisy trial Sharpes
    dsr = deflated_sharpe_ratio(rets, spread, periods_per_year=252)
    assert dsr <= psr                                  # deflation never inflates confidence


def test_walk_forward_reports_oos(sine_candle):
    grid = {"fast": [5, 10], "slow": [20, 30]}
    out = walk_forward(sine_candle, MACross, grid, n_splits=3, metric="sharpe")
    assert out["n_folds"] >= 1
    assert "avg_out_of_sample" in out
    assert "positive_folds" in out and out["positive_folds"] <= out["n_folds"]
    assert "avg_oos_psr" in out
    for fold in out["folds"]:
        assert fold["best_params"]["fast"] < fold["best_params"]["slow"]
        assert "out_of_sample" in fold
        assert 0.0 <= fold["oos_psr"] <= 1.0


def test_walk_forward_rejects_tiny_data(sine_candle):
    with pytest.raises(ValueError, match="not enough data"):
        walk_forward(sine_candle[:6], MACross, {"fast": [5], "slow": [20]}, n_splits=5)
