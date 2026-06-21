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


def test_slippage_moves_market_fill_against_taker(tmp_path):
    state = LiveState(tmp_path / "s.db")
    state.set("slippage", 0.01)          # 1% slippage
    tm = TradeManager(state, fee=0.0)
    tm.cash = 10_000.0
    # market BUY fills 1% above the quote -> 101
    tm.submit("BTCUSDT", "BUY", 1.0, 100.0, order_type="market")
    assert tm.cash == pytest.approx(9_899.0)
    assert tm.state.positions()[0]["avg_price"] == pytest.approx(101.0)
    # market SELL fills 1% below the quote -> 99
    tm.submit("BTCUSDT", "SELL", 1.0, 100.0, order_type="market")
    assert tm.cash == pytest.approx(9_998.0)


def test_limit_orders_are_not_slipped(tmp_path):
    state = LiveState(tmp_path / "s.db")
    state.set("slippage", 0.01)
    tm = TradeManager(state, fee=0.0)
    tm.cash = 10_000.0
    tm.submit("BTCUSDT", "BUY", 1.0, 100.0, order_type="limit")
    assert tm.cash == pytest.approx(9_900.0)   # rests at the limit price, no slip
    assert tm.state.positions()[0]["avg_price"] == pytest.approx(100.0)


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


def test_live_placement_failure_rejects_not_dangling(tm, monkeypatch):
    monkeypatch.setenv("YQ_ALLOW_LIVE", "1")
    trade = tm.submit("BTCUSDT", "BUY", 1.0, 100.0, mode="live")

    def boom(_t):
        raise RuntimeError("network down")

    result = tm.approve(trade["id"], place_live=boom)
    # a failed placement must not stay pending — it's rejected with the reason logged
    assert result["status"] == "rejected"
    assert tm.state.get_trade(trade["id"])["meta"]["place_error"] == "network down"


class _FakeVenue:
    name = "fake"
    def create_order(self, **kwargs):
        return {"id": "OID1"}


def test_auto_approve_executes_live_without_approval(tm, monkeypatch):
    monkeypatch.setenv("YQ_ALLOW_LIVE", "1")
    tm.state.set("auto_approve", True)          # user opt-in to hands-off live
    monkeypatch.setattr("yammyquant.exchanges.get_exchange", lambda name=None, **k: _FakeVenue())
    monkeypatch.setattr("yammyquant.exchanges.default_exchange", lambda: "fake")
    trade = tm.submit("BTCUSDT", "BUY", 1.0, 100.0, mode="live")
    assert trade["status"] == "filled"          # placed immediately, no pending queue
    assert tm.state.trades(status="pending") == []


def test_auto_approve_still_needs_live_flag(tm, monkeypatch):
    monkeypatch.delenv("YQ_ALLOW_LIVE", raising=False)
    tm.state.set("auto_approve", True)
    trade = tm.submit("BTCUSDT", "BUY", 1.0, 100.0, mode="live")
    assert trade["status"] == "pending"         # env gate holds -> not auto-executed


def test_live_without_auto_approve_stays_pending(tm, monkeypatch):
    monkeypatch.setenv("YQ_ALLOW_LIVE", "1")     # live allowed, but auto_approve off
    trade = tm.submit("BTCUSDT", "BUY", 1.0, 100.0, mode="live")
    assert trade["status"] == "pending"         # approval gate holds


def test_close_position(tm):
    tm.submit("BTCUSDT", "BUY", 2.0, 100.0)
    tm.close_position("BTCUSDT", 110.0)
    assert tm.state.positions() == []
