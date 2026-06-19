"""Discord notifications via webhook.

The old ``utils/bot.py`` hardcoded a bot token (a secret leak) and used a
broken async client. This version posts to a Discord *webhook* URL read from
the environment, which needs no token, no gateway connection, and keeps secrets
out of the source tree.

Set ``DISCORD_WEBHOOK_URL`` in your environment, then::

    DiscordNotifier().send("backtest finished: +12.3%")
"""

from __future__ import annotations

import os
from typing import Optional


class DiscordNotifier:
    def __init__(self, webhook_url: Optional[str] = None):
        self.webhook_url = webhook_url or os.getenv("DISCORD_WEBHOOK_URL")

    def send(self, message: str) -> bool:
        """Post ``message`` to the configured webhook. Returns success flag."""
        if not self.webhook_url:
            raise RuntimeError(
                "No Discord webhook configured. Set DISCORD_WEBHOOK_URL or pass webhook_url."
            )
        import requests  # optional dependency

        resp = requests.post(self.webhook_url, json={"content": message}, timeout=10)
        return resp.status_code in (200, 204)
