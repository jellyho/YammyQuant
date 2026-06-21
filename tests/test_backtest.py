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


class _ScriptedStrategy(Strategy):
    """Emits a scripted action per call index (None = hold)."""

    warmup = 1

    def __init__(self, script):
        self._script = script

    def reset(self):
        self._i = 0

    def on_bar(self, window):
        i = getattr(self, "_i", 0)
        self._i = i + 1
        act = self._script[i] if i < len(self._script) else None
        return [Order(act, window.ticker, quantity=1.0)] if act else []


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


# -- shorting --------------------------------------------------------------

def test_portfolio_short_round_trip_realizes_pnl():
    from yammyquant.backtest.portfolio import Portfolio
    from yammyquant.backtest.order import Order, Action, Fill

    p = Portfolio(cash=1_000.0, fee=0.0, allow_short=True)
    # open a short: SELL 1 @ 100 -> qty -1, cash +100
    p.apply_fill(Fill(Order(Action.SELL, "X", 1.0), fill_price=100.0, fill_quantity=1.0))
    assert p.position("X").is_short and p.position("X").quantity == -1.0
    assert p.cash == 1_100.0
    # price drops to 90 -> short is in profit; equity = cash + (-1)*90 = 1010
    p.mark(None, {"X": 90.0})
    assert p.equity() == 1_010.0
    # cover: BUY 1 @ 90 -> realized +10, flat
    p.apply_fill(Fill(Order(Action.BUY, "X", 1.0), fill_price=90.0, fill_quantity=1.0))
    assert not p.position("X").is_open
    cover = p.trades.iloc[-1]
    assert bool(cover["closing"]) and cover["realized_pnl"] == 10.0


def test_long_only_rejects_short_sell():
    from yammyquant.backtest.portfolio import Portfolio
    from yammyquant.backtest.order import Order, Action, Fill

    p = Portfolio(cash=1_000.0, fee=0.0, allow_short=False)
    ok = p.apply_fill(Fill(Order(Action.SELL, "X", 1.0), fill_price=100.0, fill_quantity=1.0))
    assert ok is False and not p.position("X").is_open


def test_short_stop_loss_triggers_above_entry():
    from yammyquant.backtest.risk import RiskConfig, RiskManager

    rm = RiskManager(RiskConfig(stop_loss=0.05, take_profit=0.10))
    # short entered at 100: stop is ABOVE (105), checked against bar high
    assert rm.exit_price(100.0, bar_high=106.0, bar_low=99.0, is_short=True) == 105.0
    # take-profit BELOW (90), checked against bar low
    assert rm.exit_price(100.0, bar_high=101.0, bar_low=89.0, is_short=True) == 90.0
    # nothing triggered
    assert rm.exit_price(100.0, bar_high=101.0, bar_low=99.0, is_short=True) is None


def test_engine_shorts_through_full_loop():
    candle = _ohlc_candle()  # opens 100,110,120,130 (rising)
    # SELL on bar0 -> short opens at bar1 open (110); BUY on bar2 -> cover at bar3 open (130)
    strat = _ScriptedStrategy([Action.SELL, None, Action.BUY])
    res = Backtest(candle, strat, cash=10_000.0, fee=0.0,
                   fill_timing="next_open", allow_short=True).run()
    assert (res.trades["action"] == "SELL").sum() == 1
    cover = res.trades[res.trades["closing"]].iloc[-1]
    # rising market -> short loses: covered at 130 vs shorted at 110 -> -20
    assert float(cover["realized_pnl"]) == -20.0
    assert res.stats["num_closed"] == 1


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
