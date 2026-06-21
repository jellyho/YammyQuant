import numpy as np
import pytest

from yammyquant.backtest.risk import RiskConfig, RiskManager
from yammyquant.backtest.engine import Backtest
from yammyquant.strategy.builtin import MACross


def test_fraction_sizing():
    rm = RiskManager(RiskConfig(sizing="fraction", risk_fraction=0.25))
    qty = rm.size_entry(equity=10_000, price=100)
    assert qty == 25.0  # 0.25 * 10000 / 100


def test_volatility_sizing_capped():
    rm = RiskManager(RiskConfig(sizing="volatility", vol_target=0.2,
                                max_position_fraction=0.5), periods_per_year=365)
    # near-zero vol → scale huge → capped at max_position_fraction
    qty = rm.size_entry(10_000, 100, recent_returns=np.full(20, 1e-9))
    assert qty == 50.0  # 0.5 * 10000 / 100


def test_stop_loss_triggers_on_low():
    rm = RiskManager(RiskConfig(stop_loss=0.05))
    assert rm.exit_price(avg_entry=100, bar_high=101, bar_low=94) == pytest.approx(95.0)
    assert rm.exit_price(avg_entry=100, bar_high=101, bar_low=96) is None


def test_take_profit_triggers_on_high():
    rm = RiskManager(RiskConfig(take_profit=0.1))
    assert rm.exit_price(avg_entry=100, bar_high=111, bar_low=99) == pytest.approx(110.0)


def test_stop_loss_precedence():
    rm = RiskManager(RiskConfig(stop_loss=0.05, take_profit=0.1))
    # both could trigger; stop-loss wins (conservative)
    assert rm.exit_price(avg_entry=100, bar_high=111, bar_low=94) == pytest.approx(95.0)


def test_drawdown_kill_switch():
    rm = RiskManager(RiskConfig(max_drawdown=0.2))
    assert rm.drawdown_breached(peak_equity=100, equity=79) is True
    assert rm.drawdown_breached(peak_equity=100, equity=85) is False


def test_engine_accepts_risk_config(sine_candle):
    risk = RiskConfig(sizing="fraction", risk_fraction=0.5,
                      stop_loss=0.05, take_profit=0.1, max_drawdown=0.3)
    result = Backtest(sine_candle, MACross(5, 20), cash=10_000, risk=risk).run()
    assert not result.equity_curve.empty
    assert "sharpe" in result.stats


def test_trailing_exit_long_and_short():
    rm = RiskManager(RiskConfig(trailing_stop=0.10))
    # long: stop trails 10% below the high-water mark (130 -> 117)
    assert rm.trailing_exit(hwm=130, bar_high=125, bar_low=116) == pytest.approx(117.0)
    assert rm.trailing_exit(hwm=130, bar_high=125, bar_low=118) is None
    # short: stop trails 10% above the low-water mark (70 -> 77)
    assert rm.trailing_exit(hwm=70, bar_high=78, bar_low=72, is_short=True) == pytest.approx(77.0)
    assert rm.trailing_exit(hwm=70, bar_high=76, bar_low=72, is_short=True) is None


def test_breakeven_exit_arms_then_fires():
    rm = RiskManager(RiskConfig(breakeven_trigger=0.05))
    # armed once hwm gained 5% (>=105); fires when price trades back to entry
    assert rm.breakeven_exit(avg_entry=100, hwm=106, bar_high=104, bar_low=99) == pytest.approx(100.0)
    # not yet armed -> no exit even if price dips to entry
    assert rm.breakeven_exit(avg_entry=100, hwm=104, bar_high=104, bar_low=99) is None


def test_trailing_stop_fires_after_runup():
    import pandas as pd
    from yammyquant.data.candle import Candle
    from yammyquant.backtest.engine import Backtest as _BT
    from tests.test_backtest import _BuyOnceStrategy

    # enter at bar1 open (100), run up to a high of 130, then pull back through
    # the 10% trail (130*0.9 = 117) on the last bar
    idx = pd.date_range("2023-01-01", periods=5, freq="1D")
    df = pd.DataFrame(
        {"open": [100, 100, 105, 128, 120],
         "high": [101, 110, 130, 129, 121],
         "low":  [99, 100, 104, 118, 115],   # bar4 low 115 <= 117 -> trailing exit
         "close": [100, 105, 128, 122, 116],
         "volume": [1.0] * 5},
        index=idx,
    )
    candle = Candle("TR", df, interval="1d")
    res = _BT(candle, _BuyOnceStrategy(), cash=10_000, fee=0.0,
              fill_timing="next_open", risk=RiskConfig(trailing_stop=0.10)).run()
    closes = res.trades[res.trades["closing"]]
    assert len(closes) == 1
    assert float(closes.iloc[0]["price"]) == pytest.approx(117.0)


def test_time_stop_exits_after_n_bars(trend_candle):
    # a long entry on a steadily rising series, forced out after 3 bars
    from yammyquant.backtest.engine import Backtest as _BT
    from tests.test_backtest import _BuyOnceStrategy
    risk = RiskConfig(max_holding_bars=3)
    res = _BT(trend_candle, _BuyOnceStrategy(), cash=10_000, fee=0.0,
              fill_timing="next_open", risk=risk).run()
    closes = res.trades[res.trades["closing"]]
    assert len(closes) == 1   # entered once, time-stopped once
