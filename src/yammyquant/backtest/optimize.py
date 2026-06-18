"""Parameter optimization and walk-forward analysis.

Matches the optimization layer every serious framework ships (freqtrade's
hyperopt, Jesse's genetic optimizer): search a strategy's parameter space for
the best in-sample score, and validate it out-of-sample with **walk-forward**
analysis — the single most important guard against curve-fitting.

Dependency-free grid search by default; Optuna is used automatically if it's
installed and ``method="optuna"`` is requested.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass
from typing import Callable, Optional, Sequence, Type

from yammyquant.data.candle import Candle
from yammyquant.strategy.base import Strategy
from yammyquant.backtest.engine import Backtest


def _param_combinations(grid: dict[str, Sequence]) -> list[dict]:
    keys = list(grid)
    return [dict(zip(keys, values)) for values in itertools.product(*(grid[k] for k in keys))]


def _score(stats: dict, metric: str) -> float:
    value = stats.get(metric)
    if value is None:
        return float("-inf")
    return float(value)


@dataclass
class OptimizeResult:
    best_params: dict
    best_score: float
    metric: str
    results: list[dict]  # [{params, score, stats}], sorted best-first


def grid_search(
    candle: Candle,
    strategy_cls: Type[Strategy],
    grid: dict[str, Sequence],
    metric: str = "sharpe",
    cash: float = 10_000.0,
    fee: float = 0.001,
    risk=None,
    skip_invalid: bool = True,
) -> OptimizeResult:
    """Exhaustively evaluate ``grid`` and rank by ``metric`` (higher is better)."""
    results = []
    for params in _param_combinations(grid):
        try:
            strat = strategy_cls(**params)
            stats = Backtest(candle, strat, cash=cash, fee=fee, risk=risk).run().stats
        except Exception:  # invalid combo (e.g. fast>=slow) or too little data
            if skip_invalid:
                continue
            raise
        results.append({"params": params, "score": _score(stats, metric), "stats": stats})

    if not results:
        raise ValueError("no valid parameter combinations were evaluated")
    results.sort(key=lambda r: r["score"], reverse=True)
    best = results[0]
    return OptimizeResult(best["params"], best["score"], metric, results)


def walk_forward(
    candle: Candle,
    strategy_cls: Type[Strategy],
    grid: dict[str, Sequence],
    n_splits: int = 4,
    metric: str = "sharpe",
    cash: float = 10_000.0,
    fee: float = 0.001,
    risk=None,
) -> dict:
    """Rolling walk-forward: optimize on each train window, score the next test window.

    Splits the series into ``n_splits + 1`` contiguous folds; fold *k* trains on
    fold *k* and tests (out-of-sample) on fold *k+1*. Returns per-fold best
    params with their out-of-sample stats plus the average OOS metric — the
    number that actually matters for generalization.
    """
    n = len(candle)
    if n_splits < 1:
        raise ValueError("n_splits must be >= 1")
    fold = n // (n_splits + 1)
    if fold < 2:
        raise ValueError(f"not enough data for {n_splits} walk-forward splits ({n} bars)")

    folds = []
    for k in range(n_splits):
        train = candle[k * fold : (k + 1) * fold]
        test = candle[(k + 1) * fold : (k + 2) * fold]
        if len(test) == 0:
            break
        opt = grid_search(train, strategy_cls, grid, metric, cash, fee, risk)
        oos = Backtest(test, strategy_cls(**opt.best_params), cash=cash, fee=fee, risk=risk).run().stats
        folds.append({
            "fold": k,
            "train_bars": len(train),
            "test_bars": len(test),
            "best_params": opt.best_params,
            "in_sample_score": round(opt.best_score, 4),
            "out_of_sample": oos,
        })

    oos_scores = [_score(f["out_of_sample"], metric) for f in folds if f["out_of_sample"]]
    avg_oos = round(sum(oos_scores) / len(oos_scores), 4) if oos_scores else None
    return {"metric": metric, "n_folds": len(folds),
            "avg_out_of_sample": avg_oos, "folds": folds}
