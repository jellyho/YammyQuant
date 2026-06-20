"""Upbit (업비트) — Korea's largest crypto exchange.

Public quotation endpoints need no auth; exchange (private) endpoints use a JWT
(HS256) built from the API access/secret keys, with a SHA512 ``query_hash`` over
the request parameters. Docs: https://docs.upbit.com / https://global-docs.upbit.com
"""

from __future__ import annotations

import hashlib
import os
import uuid
from typing import Optional
from urllib.parse import urlencode

from yammyquant.data.candle import Candle
from yammyquant.exchanges.base import Exchange, candle_from_records, jwt_hs256

# canonical interval -> Upbit minute unit (None means a non-minute endpoint)
_MINUTE_UNITS = {"1m": 1, "3m": 3, "5m": 5, "10m": 10, "15m": 15, "30m": 30,
                 "1h": 60, "4h": 240}
_NON_MINUTE = {"1d": "days", "1w": "weeks", "1M": "months"}


class UpbitExchange(Exchange):
    name = "upbit"
    asset_class = "crypto"
    supports_trading = True
    BASE = "https://api.upbit.com"

    def __init__(self, access_key: Optional[str] = None, secret_key: Optional[str] = None):
        self.access_key = access_key or os.getenv("UPBIT_ACCESS_KEY")
        self.secret_key = secret_key or os.getenv("UPBIT_SECRET_KEY")

    # -- market data -------------------------------------------------------
    def read(self, ticker: str, interval: str = "1d", count: int = 200,
             start=None, end=None) -> Candle:
        """``ticker`` is Upbit market format, e.g. ``"KRW-BTC"``."""
        path, params = self._candle_request(ticker, interval, count, end)
        raw = self._request("GET", self.BASE + path, params=params)
        return self._parse_candles(ticker, interval, raw)

    @staticmethod
    def _candle_request(ticker: str, interval: str, count: int, end) -> tuple[str, dict]:
        params: dict = {"market": ticker, "count": min(count, 200)}
        if end is not None:
            params["to"] = end if isinstance(end, str) else end.strftime("%Y-%m-%d %H:%M:%S")
        if interval in _MINUTE_UNITS:
            return f"/v1/candles/minutes/{_MINUTE_UNITS[interval]}", params
        if interval in _NON_MINUTE:
            return f"/v1/candles/{_NON_MINUTE[interval]}", params
        raise ValueError(f"unsupported Upbit interval {interval!r}")

    @staticmethod
    def _parse_candles(ticker: str, interval: str, raw: list) -> Candle:
        records = [
            {"time": r["candle_date_time_kst"], "open": r["opening_price"],
             "high": r["high_price"], "low": r["low_price"],
             "close": r["trade_price"], "volume": r["candle_acc_trade_volume"]}
            for r in raw
        ]
        return candle_from_records(ticker.replace("-", ""), interval, records)

    # -- auth --------------------------------------------------------------
    def _auth_headers(self, params: Optional[dict] = None) -> dict:
        if not self.access_key or not self.secret_key:
            raise RuntimeError("Upbit API keys required (UPBIT_ACCESS_KEY / UPBIT_SECRET_KEY)")
        payload = {"access_key": self.access_key, "nonce": str(uuid.uuid4())}
        if params:
            query = urlencode(params)
            payload["query_hash"] = hashlib.sha512(query.encode()).hexdigest()
            payload["query_hash_alg"] = "SHA512"
        return {"Authorization": f"Bearer {jwt_hs256(payload, self.secret_key)}"}

    # -- trading -----------------------------------------------------------
    def balances(self) -> dict:
        return self._request("GET", self.BASE + "/v1/accounts", headers=self._auth_headers())

    def create_order(self, ticker: str, side: str, quantity: float,
                     price: Optional[float] = None, order_type: str = "limit") -> dict:
        params = {"market": ticker, "side": "bid" if side.upper() == "BUY" else "ask"}
        if order_type == "limit":
            params.update(volume=str(quantity), price=str(price), ord_type="limit")
        elif order_type == "market":
            if side.upper() == "BUY":  # Upbit market-buy is by total KRW (price)
                params.update(price=str(price), ord_type="price")
            else:
                params.update(volume=str(quantity), ord_type="market")
        else:
            raise ValueError(f"unsupported order_type {order_type!r}")
        return self._request("POST", self.BASE + "/v1/orders",
                             headers=self._auth_headers(params), json_body=params)
