from yammyquant.state.store import LiveState


def test_inbox_roundtrip(tmp_path):
    s = LiveState(tmp_path / "s.db")
    mid = s.post_instruction("backtest ETH 1h")
    unread = s.inbox(only_unread=True)
    assert len(unread) == 1 and unread[0]["id"] == mid
    s.mark_inbox_read([mid])
    assert s.inbox(only_unread=True) == []


def test_activity_log(tmp_path):
    s = LiveState(tmp_path / "s.db")
    s.log("backtest", "ran macross", sharpe=1.2)
    rows = s.activity()
    assert rows[0]["kind"] == "backtest"
    assert rows[0]["meta"]["sharpe"] == 1.2


def test_positions_and_settings(tmp_path):
    s = LiveState(tmp_path / "s.db")
    s.upsert_position("BTCUSDT", 1.5, 100.0)
    assert s.positions()[0]["quantity"] == 1.5
    s.upsert_position("BTCUSDT", 0.0, 0.0)  # closing removes it
    assert s.positions() == []
    s.set("strategy_macross", True)
    assert s.get("strategy_macross") is True


def test_snapshot_shape(tmp_path):
    s = LiveState(tmp_path / "s.db")
    snap = s.snapshot()
    for key in ["positions", "trades", "pending_trades", "equity", "signals", "activity", "inbox", "settings"]:
        assert key in snap
