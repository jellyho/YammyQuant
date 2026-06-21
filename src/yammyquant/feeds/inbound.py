"""Inbound control — let the user steer the operator from Slack/Discord.

The outbound side (``ops/notify.py``) pushes status *to* the user. This is the
return path: poll a Slack/Discord channel for new messages and drop them into
the operator's ``inbox``, so the next ``yq recall`` / ``yq inbox`` surfaces them
and the agent (Claude Code) acts on the user's intent.

Polling, not webhooks: the cockpit runs locally/ephemerally with no public URL,
and polling mirrors the existing ``news --collect`` pattern. Configure via env
(read-only **bot** credentials, distinct from the outbound webhooks):

    DISCORD_BOT_TOKEN, DISCORD_CHANNEL_ID     # Discord
    SLACK_BOT_TOKEN,   SLACK_CHANNEL_ID       # Slack (xoxb- token, channel/conversation read scope)

A per-platform cursor is kept in settings so each message is ingested once.
The bot's own messages (and other bots) are skipped, so status pushes don't
loop back in as instructions.
"""

from __future__ import annotations

import os
from typing import Optional

from yammyquant.state.store import LiveState

_DISCORD_API = "https://discord.com/api/v10"
_SLACK_API = "https://slack.com/api"


def inbound_channels() -> list[str]:
    """Which inbound platforms are configured via env (token + channel)."""
    out = []
    if os.getenv("DISCORD_BOT_TOKEN") and os.getenv("DISCORD_CHANNEL_ID"):
        out.append("discord")
    if os.getenv("SLACK_BOT_TOKEN") and os.getenv("SLACK_CHANNEL_ID"):
        out.append("slack")
    return out


# -- raw fetchers (monkeypatched in tests; the only network seam) ----------

def _fetch_discord(token: str, channel_id: str, after_id: Optional[str]) -> list[dict]:
    import requests

    params = {"limit": 50}
    if after_id:
        params["after"] = after_id
    resp = requests.get(
        f"{_DISCORD_API}/channels/{channel_id}/messages",
        headers={"Authorization": f"Bot {token}"}, params=params, timeout=15,
    )
    resp.raise_for_status()
    return resp.json()


def _fetch_slack(token: str, channel_id: str, oldest: Optional[str]) -> list[dict]:
    import requests

    params = {"channel": channel_id, "limit": 50}
    if oldest:
        params["oldest"] = oldest
    resp = requests.get(
        f"{_SLACK_API}/conversations.history",
        headers={"Authorization": f"Bearer {token}"}, params=params, timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()
    if not data.get("ok"):
        raise RuntimeError(f"slack error: {data.get('error')}")
    return data.get("messages", [])


# -- ingestion -------------------------------------------------------------

def collect_inbound(state: LiveState) -> dict:
    """Poll every configured platform and post new user messages to the inbox.

    Returns ``{"discord": n, "slack": m, "messages": [...]}`` — how many new
    instructions were ingested per platform and their text.
    """
    ingested: list[str] = []
    counts = {"discord": 0, "slack": 0}

    if "discord" in inbound_channels():
        token, channel = os.environ["DISCORD_BOT_TOKEN"], os.environ["DISCORD_CHANNEL_ID"]
        cursor_key = "inbound.discord.last_id"
        last_id = state.get(cursor_key)
        try:
            msgs = _fetch_discord(token, channel, last_id)
        except Exception as exc:
            state.log("inbound", f"discord poll failed: {exc}", level="warn")
            msgs = []
        # Discord returns newest-first; process oldest-first for stable cursoring
        new_max = last_id
        for m in sorted(msgs, key=lambda m: int(m.get("id", 0))):
            mid = str(m.get("id"))
            # advance the cursor past every message seen (even skipped ones)
            new_max = mid if (new_max is None or int(mid) > int(new_max)) else new_max
            if last_id and int(mid) <= int(last_id):
                continue
            if (m.get("author") or {}).get("bot"):
                continue                                   # skip bots (incl. our own)
            text = (m.get("content") or "").strip()
            if text:
                author = (m.get("author") or {}).get("username", "user")
                state.post_instruction(f"[discord:{author}] {text}")
                ingested.append(text)
                counts["discord"] += 1
        if new_max and new_max != last_id:
            state.set(cursor_key, new_max)

    if "slack" in inbound_channels():
        token, channel = os.environ["SLACK_BOT_TOKEN"], os.environ["SLACK_CHANNEL_ID"]
        cursor_key = "inbound.slack.last_ts"
        last_ts = state.get(cursor_key)
        try:
            msgs = _fetch_slack(token, channel, last_ts)
        except Exception as exc:
            state.log("inbound", f"slack poll failed: {exc}", level="warn")
            msgs = []
        new_ts = last_ts
        for m in sorted(msgs, key=lambda m: float(m.get("ts", 0))):
            ts = m.get("ts")
            new_ts = ts if (new_ts is None or float(ts) > float(new_ts)) else new_ts
            if last_ts and float(ts) <= float(last_ts):
                continue
            if m.get("bot_id") or m.get("subtype"):        # skip bots / joins / edits
                continue
            text = (m.get("text") or "").strip()
            if text:
                state.post_instruction(f"[slack:{m.get('user', 'user')}] {text}")
                ingested.append(text)
                counts["slack"] += 1
        if new_ts and new_ts != last_ts:
            state.set(cursor_key, new_ts)

    total = counts["discord"] + counts["slack"]
    if total:
        state.log("inbound", f"ingested {total} instruction(s) from "
                  f"{', '.join(k for k, v in counts.items() if v)}")
    return {**counts, "messages": ingested}
