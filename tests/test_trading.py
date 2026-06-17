import pytest

from yammyquant.state.store import LiveState
from yammyquant.ops.trading import TradeManager


@pytest.fixture
def tm(tmp_path):
    state = LiveState(tmp_path / "s.db")
    manager = TradeManager(state, fee=0.0)
    manager.cash = 10_000.0
    return manager


def test_paper_buy_fills_and_updates(tm):
    trade = tm.submit("BTCUSDT", "BUY", 1.0, 100.0, mode="paper")
    assert trade["status"] == "filled"
    assert tm.cash == 9_900.0
    assert tm.state.positions()[0]["quantity"] == 1.0


def test_paper_sell_realizes(tm):
    tm.submit("BTCUSDT", "BUY", 1.0, 100.0)
    tm.submit("BTCUSDT", "SELL", 1.0, 120.0)
    assert tm.cash == 10_020.0
    assert tm.state.positions() == []


def test_insufficient_cash_rejected(tm):
    tm.cash = 50.0
    trade = tm.submit("BTCUSDT", "BUY", 1.0, 100.0)
    assert trade["status"] == "rejected"
    assert tm.cash == 50.0


def test_live_trade_queues_pending(tm):
    trade = tm.submit("BTCUSDT", "BUY", 1.0, 100.0, mode="live")
    assert trade["status"] == "pending"
    assert tm.cash == 10_000.0  # nothing moved yet


def test_live_approval_blocked_without_flag(tm, monkeypatch):
    monkeypatch.delenv("YQ_ALLOW_LIVE", raising=False)
    trade = tm.submit("BTCUSDT", "BUY", 1.0, 100.0, mode="live")
    result = tm.approve(trade["id"])
    assert result["status"] == "rejected"  # YQ_ALLOW_LIVE not set


def test_live_approval_with_flag_uses_placer(tm, monkeypatch):
    monkeypatch.setenv("YQ_ALLOW_LIVE", "1")
    trade = tm.submit("BTCUSDT", "BUY", 1.0, 100.0, mode="live")
    placed = {}
    tm.approve(trade["id"], place_live=lambda t: placed.update(t))
    assert placed["ticker"] == "BTCUSDT"
    assert tm.state.get_trade(trade["id"])["status"] == "filled"


def test_close_position(tm):
    tm.submit("BTCUSDT", "BUY", 2.0, 100.0)
    tm.close_position("BTCUSDT", 110.0)
    assert tm.state.positions() == []
