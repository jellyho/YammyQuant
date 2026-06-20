
import pytest

from yammyquant.state.store import LiveState
from yammyquant.ops.trading import TradeManager
from yammyquant.ops.risk_policy import AccountRiskPolicy, check_order


@pytest.fixture
def tm(tmp_path):
    state = LiveState(tmp_path / "s.db")
    m = TradeManager(state, fee=0.0)
    m.cash = 100_000.0
    return m


def test_max_order_value_blocks(tm):
    AccountRiskPolicy(max_order_value=500).save(tm.state)
    trade = tm.submit("AAA", "BUY", 10, 100)  # 1000 > 500
    assert trade["status"] == "rejected"
    assert tm.state.positions() == []


def test_max_open_positions_blocks(tm):
    AccountRiskPolicy(max_open_positions=1).save(tm.state)
    assert tm.submit("AAA", "BUY", 1, 100)["status"] == "filled"
    assert tm.submit("BBB", "BUY", 1, 100)["status"] == "rejected"


def test_max_symbol_weight_blocks(tm):
    AccountRiskPolicy(max_symbol_weight=0.1).save(tm.state)  # 10% of 100k = 10k
    assert tm.submit("AAA", "BUY", 50, 100)["status"] == "filled"      # 5k ok
    assert tm.submit("AAA", "BUY", 100, 100)["status"] == "rejected"   # +10k -> 15k > 10k


def test_sells_always_allowed(tm):
    tm.submit("AAA", "BUY", 10, 100)
    AccountRiskPolicy(max_order_value=1).save(tm.state)  # would block any buy
    assert tm.submit("AAA", "SELL", 10, 110)["status"] == "filled"


def test_daily_loss_limit_blocks_after_loss(tm):
    tm.submit("AAA", "BUY", 10, 100)
    tm.submit("AAA", "SELL", 10, 90)  # realized -100
    AccountRiskPolicy(daily_loss_limit=50).save(tm.state)
    assert tm.submit("BBB", "BUY", 1, 100)["status"] == "rejected"


def test_cooldown_blocks_rapid_reentry(tm):
    AccountRiskPolicy(cooldown_minutes=60).save(tm.state)
    tm.submit("AAA", "BUY", 1, 100)
    assert tm.submit("AAA", "BUY", 1, 100)["status"] == "rejected"


def test_check_order_allows_within_limits(tmp_path):
    state = LiveState(tmp_path / "s.db")
    AccountRiskPolicy(max_order_value=10_000).save(state)
    assert check_order(state, "AAA", "BUY", 1, 100, equity=100_000) is None
