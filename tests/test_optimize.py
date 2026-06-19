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


def test_walk_forward_reports_oos(sine_candle):
    grid = {"fast": [5, 10], "slow": [20, 30]}
    out = walk_forward(sine_candle, MACross, grid, n_splits=3, metric="sharpe")
    assert out["n_folds"] >= 1
    assert "avg_out_of_sample" in out
    for fold in out["folds"]:
        assert fold["best_params"]["fast"] < fold["best_params"]["slow"]
        assert "out_of_sample" in fold


def test_walk_forward_rejects_tiny_data(sine_candle):
    with pytest.raises(ValueError, match="not enough data"):
        walk_forward(sine_candle[:6], MACross, {"fast": [5], "slow": [20]}, n_splits=5)
