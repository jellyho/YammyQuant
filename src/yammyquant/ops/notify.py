"""Operator notifications — log to state and ping the user when action is needed.

Centralizes the "tell the human" path so events that need eyes (a live order
awaiting approval, a stop/risk rejection, a drawdown breach, an error) reach the
user via Discord and/or Slack, while always leaving a trace in the activity log.
Webhooks are read from env; if none is set, it degrades to log-only.
"""

from __future__ import annotations

import os

from yammyquant.state.store import LiveState


def webhook_url() -> str | None:
    """Back-compat alias for the Discord webhook."""
    return os.getenv("DISCORD_WEBHOOK_URL")


def channels() -> list[str]:
    """Which notification channels are configured via env."""
    out = []
    if os.getenv("DISCORD_WEBHOOK_URL"):
        out.append("discord")
    if os.getenv("SLACK_WEBHOOK_URL"):
        out.append("slack")
    return out


def notify(state: LiveState, message: str, level: str = "info") -> bool:
    """Log the notification and fan it out to every configured channel.

    ``level`` is one of info/action/warn/error. Returns whether any push was
    sent. Never raises — notification failures must not break trading.
    """
    state.log("notify", message, level=level)
    text = f"[YammyQuant·{level}] {message}"
    sent = False
    if os.getenv("DISCORD_WEBHOOK_URL"):
        try:
            from yammyquant.notify.discord import DiscordNotifier

            sent = DiscordNotifier().send(text) or sent
        except Exception:
            pass
    if os.getenv("SLACK_WEBHOOK_URL"):
        try:
            from yammyquant.notify.slack import SlackNotifier

            sent = SlackNotifier().send(text) or sent
        except Exception:
            pass
    return sent
