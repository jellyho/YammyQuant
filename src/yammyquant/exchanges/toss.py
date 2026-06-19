"""Toss Securities (토스증권) — Open API (KRX + US stocks).

Toss Securities launched an OAuth2 REST Open API in 2026 (staged rollout for
pre-applicants): market data, account/portfolio, and order placement for both
Korean (KRX) and US equities. Apply at https://corp.tossinvest.com/ko/open-api ;
official docs at https://developers.tossinvest.com/docs.

.. warning::
   The exact request paths are published only on the developer portal (behind
   sign-in / staged rollout), so the ``*_PATH`` constants below are **placeholders
   to confirm against the official docs** once your application is approved. The
   OAuth2 token flow, bearer auth, candle parsing, and order building are real
   and unit-tested with mocks; override ``base_url`` / the path constants (or set
   the ``TOSS_BASE_URL`` env var) to match the published spec.
"""

from __future__ import annotations

import os
from typing import Optional

from yammyquant.data.candle import Candle
from yammyquant.exchanges.base import Exchange, candle_from_records

# Common OHLC field aliases so parsing survives the real field names.
_OPEN = ("open", "openPrice", "o")
_HIGH = ("high", "highPrice", "h")
_LOW = ("low", "lowPrice", "l")
_CLOSE = ("close", "closePrice", "c", "price")
_VOL = ("volume", "vol", "v", "tradingVolume")
_TIME = ("date", "dateTime", "timestamp", "ts", "baseDate")


def _pick(row: dict, names: tuple[str, ...]):
    for n in names:
        if n in row and row[n] is not None:
            return row[n]
    raise KeyError(f"none of {names} present in candle row {list(row)}")


class TossSecurities(Exchange):
    name = "toss"
    asset_class = "stock"
    supports_trading = True

    # ⚠️ Confirm these against https://developers.tossinvest.com/docs
    TOKEN_PATH = "/oauth2/token"
    CANDLES_PATH = "/api/v1/market/candles"
    BALANCE_PATH = "/api/v1/account/balance"
    ORDER_PATH = "/api/v1/order"

    def __init__(self, app_key: Optional[str] = None, app_secret: Optional[str] = None,
                 account: Optional[str] = None, base_url: Optional[str] = None,
                 market: str = "kr"):
        self.app_key = app_key or os.getenv("TOSS_APP_KEY")
        self.app_secret = app_secret or os.getenv("TOSS_APP_SECRET")
        self.account = account or os.getenv("TOSS_ACCOUNT", "")
        self.base = (base_url or os.getenv("TOSS_BASE_URL", "https://openapi.tossinvest.com")).rstrip("/")
        self.market = market  # "kr" or "us"
        self._token: Optional[str] = None

    # -- auth --------------------------------------------------------------
    def token(self) -> str:
        if self._token:
            return self._token
        resp = self._request("POST", self.base + self.TOKEN_PATH, json_body={
            "grant_type": "client_credentials",
            "appKey": self.app_key, "appSecret": self.app_secret,
        })
        self._token = resp.get("access_token") or resp.get("accessToken")
        if not self._token:
            raise RuntimeError(f"Toss token response missing access token: {list(resp)}")
        return self._token

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.token()}",
                "Content-Type": "application/json"}

    # -- market data -------------------------------------------------------
    def read(self, ticker: str, interval: str = "1d", count: int = 200,
             start=None, end=None) -> Candle:
        """``ticker`` is the venue symbol (KRX 6-digit code, or US ticker)."""
        params = {"symbol": ticker, "market": self.market,
                  "interval": "1m" if interval == "1m" else "1d", "count": count}
        raw = self._request("GET", self.base + self.CANDLES_PATH,
                            headers=self._headers(), params=params)
        return self._parse_candles(ticker, interval, raw)

    @staticmethod
    def _parse_candles(ticker: str, interval: str, raw) -> Candle:
        rows = raw if isinstance(raw, list) else (raw.get("candles") or raw.get("data") or [])
        records = [
            {"time": _pick(r, _TIME), "open": _pick(r, _OPEN), "high": _pick(r, _HIGH),
             "low": _pick(r, _LOW), "close": _pick(r, _CLOSE), "volume": _pick(r, _VOL)}
            for r in rows
        ]
        return candle_from_records(ticker, interval, records)

    # -- trading -----------------------------------------------------------
    def balances(self) -> dict:
        return self._request("GET", self.base + self.BALANCE_PATH,
                            headers=self._headers(), params={"account": self.account})

    def create_order(self, ticker: str, side: str, quantity: float,
                     price: Optional[float] = None, order_type: str = "limit") -> dict:
        body = {
            "account": self.account, "symbol": ticker, "market": self.market,
            "side": side.upper(), "orderType": order_type.upper(),
            "quantity": quantity, "price": price,
        }
        return self._request("POST", self.base + self.ORDER_PATH,
                            headers=self._headers(), json_body=body)
