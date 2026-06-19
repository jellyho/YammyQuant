from datetime import datetime

from yammyquant.backtest.order import Action, Order, Fill
from yammyquant.backtest.portfolio import Portfolio


def _fill(action, qty, price, fee=0.0):
    return Fill(Order(action, "BTCUSDT", qty, price), price, qty, fee, datetime(2023, 1, 1))


def test_buy_then_sell_realizes_pnl():
    p = Portfolio(cash=1000.0, fee=0.0)
    assert p.apply_fill(_fill(Action.BUY, 1.0, 100.0))
    assert p.cash == 900.0
    assert p.position("BTCUSDT").quantity == 1.0
    assert p.position("BTCUSDT").avg_price == 100.0

    assert p.apply_fill(_fill(Action.SELL, 1.0, 120.0))
    assert p.cash == 1020.0
    assert p.position("BTCUSDT").quantity == 0.0
    realized = p.trades.iloc[-1]["realized_pnl"]
    assert realized == 20.0


def test_buy_rejected_when_insufficient_cash():
    p = Portfolio(cash=50.0, fee=0.0)
    assert not p.apply_fill(_fill(Action.BUY, 1.0, 100.0))
    assert p.cash == 50.0


def test_sell_rejected_without_holdings():
    p = Portfolio(cash=1000.0, fee=0.0)
    assert not p.apply_fill(_fill(Action.SELL, 1.0, 100.0))


def test_fees_reduce_cash():
    p = Portfolio(cash=1000.0, fee=0.01)
    p.apply_fill(_fill(Action.BUY, 1.0, 100.0, fee=1.0))
    assert p.cash == 899.0  # 100 notional + 1 fee


def test_average_price_on_scale_in():
    p = Portfolio(cash=10_000.0, fee=0.0)
    p.apply_fill(_fill(Action.BUY, 1.0, 100.0))
    p.apply_fill(_fill(Action.BUY, 1.0, 200.0))
    assert p.position("BTCUSDT").avg_price == 150.0


def test_equity_marks_to_market():
    p = Portfolio(cash=1000.0, fee=0.0)
    p.apply_fill(_fill(Action.BUY, 1.0, 100.0))
    p.mark(datetime(2023, 1, 2), {"BTCUSDT": 150.0})
    assert p.equity() == 900.0 + 150.0
