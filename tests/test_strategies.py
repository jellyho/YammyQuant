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
