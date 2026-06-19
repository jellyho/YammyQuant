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
