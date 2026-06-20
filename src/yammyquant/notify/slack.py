"""Slack notifications via an incoming webhook.

Like the Discord notifier, this posts to a webhook URL (no bot token, no
gateway), keeping secrets out of the source tree. Set ``SLACK_WEBHOOK_URL`` in
your environment, then::

    SlackNotifier().send("backtest finished: +12.3%")
"""

from __future__ import annotations

import os
from typing import Optional


class SlackNotifier:
    def __init__(self, webhook_url: Optional[str] = None):
        self.webhook_url = webhook_url or os.getenv("SLACK_WEBHOOK_URL")

    def send(self, message: str) -> bool:
        """Post ``message`` to the configured webhook. Returns success flag."""
        if not self.webhook_url:
            raise RuntimeError(
                "No Slack webhook configured. Set SLACK_WEBHOOK_URL or pass webhook_url."
            )
        import requests  # optional dependency

        resp = requests.post(self.webhook_url, json={"text": message}, timeout=10)
        return resp.status_code == 200
