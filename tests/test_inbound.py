"""Inbound control: Slack/Discord messages -> operator inbox (network mocked)."""

import yammyquant.feeds.inbound as inbound
from yammyquant.state.store import LiveState
from yammyquant.ops import operator as ops


def _discord_env(monkeypatch):
    monkeypatch.setenv("DISCORD_BOT_TOKEN", "tok")
    monkeypatch.setenv("DISCORD_CHANNEL_ID", "123")
    monkeypatch.delenv("SLACK_BOT_TOKEN", raising=False)
    monkeypatch.delenv("SLACK_CHANNEL_ID", raising=False)


def test_discord_ingest_skips_bots_and_dedupes(tmp_path, monkeypatch):
    _discord_env(monkeypatch)
    state = LiveState(tmp_path / "s.db")

    batch1 = [
        {"id": "10", "content": "go long BTC", "author": {"username": "jellyho"}},
        {"id": "11", "content": "status?", "author": {"username": "bot", "bot": True}},
    ]
    monkeypatch.setattr(inbound, "_fetch_discord", lambda t, c, after: batch1)
    out = ops.listen(state)
    assert out["discord"] == 1                       # bot message skipped
    unread = [m["message"] for m in state.inbox(only_unread=True)]
    assert any("go long BTC" in m for m in unread)
    assert state.get("inbound.discord.last_id") == "11"   # cursor advances past all seen ids

    # second poll returns nothing new past the cursor -> no duplicates
    monkeypatch.setattr(inbound, "_fetch_discord",
                        lambda t, c, after: [{"id": "10", "content": "go long BTC",
                                              "author": {"username": "jellyho"}}])
    out2 = ops.listen(state)
    assert out2["discord"] == 0
    assert len(state.inbox()) == 1


def test_inbound_command_parsing(tmp_path):
    state = LiveState(tmp_path / "s.db")
    # bare keyword acts
    assert ops.apply_inbound_command(state, "disarm")["command"] == "disarm"
    assert state.get("auto_approve") is False
    assert ops.apply_inbound_command(state, "arm")["command"] == "arm"
    assert state.get("auto_approve") is True
    # explicit prefix acts even with extra words
    assert ops.apply_inbound_command(state, "/pause now")["command"] == "pause"
    assert state.get("auto_trade") is False
    # prose that merely mentions a verb is ignored (no prefix, multiple words)
    assert ops.apply_inbound_command(state, "should we arm the scalper today?") is None
    # unknown verbs are ignored
    assert ops.apply_inbound_command(state, "buy BTC") is None
    # flat with no positions is a safe no-op
    assert "no open positions" in ops.apply_inbound_command(state, "flat")["detail"]


def test_inbound_command_executes_on_ingest(tmp_path, monkeypatch):
    _discord_env(monkeypatch)
    state = LiveState(tmp_path / "s.db")
    state.set("auto_approve", True)
    monkeypatch.setattr(inbound, "_fetch_discord",
                        lambda t, c, after: [{"id": "20", "content": "disarm",
                                              "author": {"username": "jellyho"}}])
    out = ops.listen(state)
    assert out["commands"] and out["commands"][0]["command"] == "disarm"
    assert state.get("auto_approve") is False     # remote command took effect
    # still recorded in the inbox for the log
    assert any("disarm" in m["message"] for m in state.inbox())


def test_slack_ingest(tmp_path, monkeypatch):
    monkeypatch.delenv("DISCORD_BOT_TOKEN", raising=False)
    monkeypatch.delenv("DISCORD_CHANNEL_ID", raising=False)
    monkeypatch.setenv("SLACK_BOT_TOKEN", "xoxb-x")
    monkeypatch.setenv("SLACK_CHANNEL_ID", "C1")
    state = LiveState(tmp_path / "s.db")

    msgs = [
        {"ts": "1000.1", "text": "reduce risk", "user": "U1"},
        {"ts": "1000.2", "text": "auto from bot", "bot_id": "B1"},   # skipped
    ]
    monkeypatch.setattr(inbound, "_fetch_slack", lambda t, c, oldest: msgs)
    out = ops.listen(state)
    assert out["slack"] == 1
    assert state.get("inbound.slack.last_ts") == "1000.2"
    assert any("reduce risk" in m["message"] for m in state.inbox(only_unread=True))


def test_no_channels_configured_is_noop(tmp_path, monkeypatch):
    for var in ("DISCORD_BOT_TOKEN", "DISCORD_CHANNEL_ID", "SLACK_BOT_TOKEN", "SLACK_CHANNEL_ID"):
        monkeypatch.delenv(var, raising=False)
    state = LiveState(tmp_path / "s.db")
    out = ops.listen(state)
    assert out["discord"] == 0 and out["slack"] == 0 and out["channels"] == []


def test_poll_failure_does_not_raise(tmp_path, monkeypatch):
    _discord_env(monkeypatch)
    state = LiveState(tmp_path / "s.db")

    def boom(*a, **k):
        raise RuntimeError("network down")

    monkeypatch.setattr(inbound, "_fetch_discord", boom)
    out = ops.listen(state)            # degrades gracefully, logs a warning
    assert out["discord"] == 0
