"""Notifications: Slack/Discord fan-out and the status digest (no network)."""

from yammyquant.state.store import LiveState
from yammyquant.ops import notify as notif
from yammyquant.ops import operator as ops


def test_channels_reflect_env(monkeypatch):
    monkeypatch.delenv("DISCORD_WEBHOOK_URL", raising=False)
    monkeypatch.delenv("SLACK_WEBHOOK_URL", raising=False)
    assert notif.channels() == []
    monkeypatch.setenv("SLACK_WEBHOOK_URL", "http://x/slack")
    assert notif.channels() == ["slack"]
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", "http://x/disc")
    assert set(notif.channels()) == {"discord", "slack"}


def test_notify_fans_out_to_both(tmp_path, monkeypatch):
    sent = []
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", "http://x/disc")
    monkeypatch.setenv("SLACK_WEBHOOK_URL", "http://x/slack")
    import yammyquant.notify.discord as d
    import yammyquant.notify.slack as s
    monkeypatch.setattr(d.DiscordNotifier, "send", lambda self, m: sent.append(("d", m)) or True)
    monkeypatch.setattr(s.SlackNotifier, "send", lambda self, m: sent.append(("s", m)) or True)

    state = LiveState(tmp_path / "s.db")
    assert notif.notify(state, "hello", "info") is True
    assert {c for c, _ in sent} == {"d", "s"}
    assert all("hello" in m for _, m in sent)
    # always logged, even though pushed
    assert any("hello" in a["summary"] for a in state.activity())


def test_notify_logs_when_no_channel(tmp_path, monkeypatch):
    monkeypatch.delenv("DISCORD_WEBHOOK_URL", raising=False)
    monkeypatch.delenv("SLACK_WEBHOOK_URL", raising=False)
    state = LiveState(tmp_path / "s.db")
    assert notif.notify(state, "logged only") is False
    assert any("logged only" in a["summary"] for a in state.activity())


def test_notify_never_raises_on_send_failure(tmp_path, monkeypatch):
    monkeypatch.setenv("SLACK_WEBHOOK_URL", "http://x/slack")
    import yammyquant.notify.slack as s

    def boom(self, m):
        raise RuntimeError("network down")

    monkeypatch.setattr(s.SlackNotifier, "send", boom)
    state = LiveState(tmp_path / "s.db")
    assert notif.notify(state, "still fine") is False   # swallowed


def test_status_digest(tmp_path, monkeypatch):
    monkeypatch.delenv("DISCORD_WEBHOOK_URL", raising=False)
    monkeypatch.delenv("SLACK_WEBHOOK_URL", raising=False)
    state = LiveState(tmp_path / "s.db")
    state.upsert_position("BTCUSDT", 0.5, 60000)
    out = ops.notify_status(state)
    assert "status" in out["message"] and "positions 1" in out["message"]
    assert out["channels"] == []


def test_status_digest_includes_edge_health(tmp_path, monkeypatch):
    from yammyquant.ops.trading import TradeManager
    monkeypatch.delenv("DISCORD_WEBHOOK_URL", raising=False)
    monkeypatch.delenv("SLACK_WEBHOOK_URL", raising=False)
    state = LiveState(tmp_path / "s.db")
    tm = TradeManager(state, fee=0.0)
    tm.cash = 10_000.0
    tm.submit("AAA", "BUY", 10, 100)
    tm.submit("AAA", "SELL", 10, 120)   # +200, a closed round-trip exists
    out = ops.notify_status(state)
    assert "win" in out["message"] and "exp" in out["message"]
