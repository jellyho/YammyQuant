"""Operator notifications — log to state and ping the user when action is needed.

Centralizes the "tell the human" path so events that need eyes (a live order
awaiting approval, a stop/risk rejection, a drawdown breach, an error) reach the
user via Discord, while always leaving a trace in the activity log. The webhook
is read from config/env; if none is set, it degrades to log-only.
"""

from __future__ import annotations

import os

from yammyquant.state.store import LiveState


def webhook_url() -> str | None:
    return os.getenv("DISCORD_WEBHOOK_URL")


def notify(state: LiveState, message: str, level: str = "info") -> bool:
    """Record a notification in the activity log and send it to Discord if configured.

    ``level`` is one of info/action/warn/error. Returns whether a push was sent.
    Never raises — notification failures must not break trading.
    """
    state.log("notify", message, level=level)
    url = webhook_url()
    if not url:
        return False
    try:
        from yammyquant.notify.discord import DiscordNotifier

        return DiscordNotifier(url).send(f"[YammyQuant·{level}] {message}")
    except Exception:
        return False
