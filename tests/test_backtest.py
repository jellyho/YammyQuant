import pandas as pd

from yammyquant.backtest.engine import Backtest, BacktestResult
from yammyquant.backtest.order import Action, Order
from yammyquant.data.candle import Candle
from yammyquant.strategy.base import Strategy
from yammyquant.strategy.builtin import MACross, VolatilityBreakout


class _BuyOnceStrategy(Strategy):
    """Emits a single BUY on the very first eligible bar, then holds."""

    warmup = 1

    def reset(self):
        self._fired = False

    def on_bar(self, window):
        if getattr(self, "_fired", False):
            return []
        self._fired = True
        return [Order(Action.BUY, window.ticker, quantity=1.0)]


def _ohlc_candle():
    # open and close differ each bar so a fill price reveals which bar/field filled
    idx = pd.date_range("2023-01-01", periods=4, freq="1D")
    df = pd.DataFrame(
        {"open": [100.0, 110.0, 120.0, 130.0],
         "high": [105.0, 115.0, 125.0, 135.0],
         "low": [95.0, 105.0, 115.0, 125.0],
         "close": [101.0, 111.0, 121.0, 131.0],
         "volume": [1.0, 1.0, 1.0, 1.0]},
        index=idx,
    )
    return Candle("T", df, interval="1d")


def test_fill_timing_next_open_fills_at_next_bar_open():
    candle = _ohlc_candle()
    # BUY decided on bar 0 (close 101) should fill at bar 1's OPEN (110), not close 101
    res = Backtest(candle, _BuyOnceStrategy(), cash=10_000.0, fee=0.0,
                   fill_timing="next_open").run()
    buys = res.trades[res.trades["action"] == "BUY"]
    assert len(buys) == 1
    assert float(buys.iloc[0]["price"]) == 110.0


def test_fill_timing_close_is_legacy_same_bar():
    candle = _ohlc_candle()
    # legacy mode fills on the signal bar's own close (101)
    res = Backtest(candle, _BuyOnceStrategy(), cash=10_000.0, fee=0.0,
                   fill_timing="close").run()
    buys = res.trades[res.trades["action"] == "BUY"]
    assert len(buys) == 1
    assert float(buys.iloc[0]["price"]) == 101.0


def test_fill_timing_rejects_bad_value():
    try:
        Backtest(_ohlc_candle(), _BuyOnceStrategy(), fill_timing="bogus")
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError for bad fill_timing")


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
                "best_trade", "worst_trade", "expectancy"]:
        assert key in result.stats


def test_expectancy_is_mean_pnl():
    import pandas as pd
    from yammyquant.metrics.performance import expectancy

    assert expectancy(pd.Series(dtype=float)) == 0.0
    # 2 wins (+200, +100) and 1 loss (-90) -> mean = 70
    assert expectancy(pd.Series([200.0, 100.0, -90.0])) == 70.0


def test_not_enough_data_raises(sine_candle):
    short = sine_candle[:10]
    bt = Backtest(short, MACross(5, 20))
    try:
        bt.run()
        assert False, "expected ValueError"
    except ValueError:
        pass
