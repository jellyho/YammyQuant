from yammyquant.backtest.engine import Backtest, BacktestResult
from yammyquant.strategy.builtin import MACross, VolatilityBreakout


def test_macross_runs_and_trades(sine_candle):
    bt = Backtest(sine_candle, MACross(5, 20, size=1.0), cash=10_000.0, fee=0.001)
    result = bt.run()
    assert isinstance(result, BacktestResult)
    assert not result.equity_curve.empty
    # an oscillating series should produce several crossover trades
    assert result.stats["num_trades"] > 0


def test_equity_curve_length_matches_bars(trend_candle):
    strat = MACross(5, 20)
    bt = Backtest(trend_candle, strat, cash=10_000.0)
    result = bt.run()
    expected = len(trend_candle) - (strat.warmup - 1)
    assert len(result.equity_curve) == expected


def test_volatility_breakout_runs(sine_candle):
    bt = Backtest(sine_candle, VolatilityBreakout(0.5), cash=10_000.0)
    result = bt.run()
    assert "sharpe" in result.stats
    assert "max_drawdown" in result.stats


def test_expanded_metrics_present(sine_candle):
    result = Backtest(sine_candle, MACross(5, 20), cash=10_000.0).run()
    for key in ["sortino", "calmar", "annual_volatility", "avg_win", "avg_loss",
                "best_trade", "worst_trade"]:
        assert key in result.stats


def test_not_enough_data_raises(sine_candle):
    short = sine_candle[:10]
    bt = Backtest(short, MACross(5, 20))
    try:
        bt.run()
        assert False, "expected ValueError"
    except ValueError:
        pass
