"""DART (전자공시, 금융감독원) — Korean corporate disclosures.

Free open API (needs a keyless-to-register key: ``DART_API_KEY``). Fetches recent
filings for a company by its 8-digit DART ``corp_code``. Parsing is pure and
tested; the network fetch needs the key + egress.
Docs: https://opendart.fss.or.kr
"""

from __future__ import annotations

import os
from typing import Optional

from yammyquant.feeds.base import NewsItem

_BASE = "https://opendart.fss.or.kr/api/list.json"
_VIEWER = "https://dart.fss.or.kr/dsaf001/main.do?rcpNo="


def parse_disclosures(payload: dict, symbol: str = "") -> list[NewsItem]:
    """Turn a DART list.json response into NewsItems."""
    items = []
    for row in payload.get("list", []):
        name = row.get("corp_name", "")
        report = row.get("report_nm", "")
        items.append(NewsItem(
            title=f"[{name}] {report}".strip(),
            url=_VIEWER + row.get("rcept_no", ""),
            source="DART",
            summary=row.get("rm", ""),
            published=row.get("rcept_dt", ""),
            symbol=symbol,
        ))
    return items


class DartFeed:
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("DART_API_KEY")

    def disclosures(self, corp_code: str, symbol: str = "", count: int = 20) -> list[NewsItem]:
        import requests  # optional dependency

        if not self.api_key:
            raise RuntimeError("DART_API_KEY required (free at opendart.fss.or.kr)")
        resp = requests.get(_BASE, timeout=15, params={
            "crtfc_key": self.api_key, "corp_code": corp_code,
            "page_count": count, "sort": "date", "sort_mth": "desc",
        })
        resp.raise_for_status()
        return parse_disclosures(resp.json(), symbol=symbol)
