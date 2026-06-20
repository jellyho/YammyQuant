import pytest

from yammyquant.backtest.engine import Backtest
from yammyquant.strategy.builtin import RSIReversion, DonchianBreakout
from yammyquant.ops.operator import STRATEGIES, DEFAULT_GRIDS, enabled_strategies
from yammyquant.state.store import LiveState


def test_new_strategies_registered():
    assert "rsi_reversion" in STRATEGIES
    assert "donchian_breakout" in STRATEGIES


@pytest.mark.parametrize("name", sorted(STRATEGIES))
def test_every_strategy_backtests(name, sine_candle, trend_candle):
    """Each registered strategy builds with defaults and runs without error."""
    for candle in (sine_candle, trend_candle):
        result = Backtest(candle, STRATEGIES[name](), cash=10_000).run()
        assert "sharpe" in result.stats
        assert result.stats["num_trades"] >= 0


def test_every_strategy_has_optimize_grid():
    assert set(DEFAULT_GRIDS) == set(STRATEGIES)


def test_rsi_reversion_runs(sine_candle):
    result = Backtest(sine_candle, RSIReversion(14), cash=10_000).run()
    assert "sharpe" in result.stats


def test_donchian_breakout_trades_on_trend(trend_candle):
    result = Backtest(trend_candle, DonchianBreakout(10), cash=10_000).run()
    # a steadily rising series should trigger at least one breakout buy
    assert result.stats["num_trades"] >= 1


def test_enabled_strategies_default_all(tmp_path):
    state = LiveState(tmp_path / "s.db")
    assert set(enabled_strategies(state)) == set(STRATEGIES)


def test_disable_strategy(tmp_path):
    state = LiveState(tmp_path / "s.db")
    state.set("strategy.macross.enabled", False)
    assert "macross" not in enabled_strategies(state)
    assert "donchian_breakout" in enabled_strategies(state)


@pytest.fixture
def gbm_candles():
    """A few realistic random-walk series — long enough that every strategy
    should trade at least once (guards the 'indicator never warms / never
    fires' class of bugs, e.g. CCI/ADX/SuperTrend warmups)."""
    import numpy as np
    import pandas as pd
    from yammyquant.data.candle import Candle
    out = []
    for seed in (1, 2, 3, 7, 42):
        rng = np.random.default_rng(seed)
        close = 100 * np.exp(np.cumsum(rng.normal(0.0004, 0.02, 500)))
        idx = pd.date_range("2022-01-01", periods=500, freq="1D")
        df = pd.DataFrame({"open": close, "high": close * 1.012, "low": close * 0.988,
                           "close": close, "volume": rng.uniform(800, 2200, 500)}, index=idx)
        out.append(Candle("X", df, interval="1d"))
    return out


@pytest.mark.parametrize("name", sorted(STRATEGIES))
def test_strategy_trades_on_realistic_data(name, gbm_candles):
    """Every registered strategy must produce >=1 trade on a long realistic
    series — a near-flat equity from zero trades is the bug we keep catching."""
    counts = [Backtest(c, STRATEGIES[name](), cash=10_000, fee=0.001).run().stats["num_trades"]
              for c in gbm_candles]
    assert min(counts) >= 1, f"{name} made 0 trades on some seed: {counts}"
