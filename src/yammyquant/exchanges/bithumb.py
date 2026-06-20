"""Bithumb (빗썸) — major Korean crypto exchange, **API 2.0**.

Bithumb retired its classic ``/public`` + HMAC-SHA512 ``/info`` ``/trade`` API in
favour of an Upbit-compatible REST 2.0: public quotation endpoints under
``/v1/candles/*`` (no auth) and private endpoints (``/v1/accounts``,
``/v1/orders``, ``/v1/order``) authenticated with a JWT (HS256) carrying a
SHA512 ``query_hash`` over the request parameters — the exact scheme Upbit uses.
Markets are ``KRW-BTC`` style. Docs: https://apidocs.bithumb.com
"""

from __future__ import annotations

import hashlib
import os
import uuid
from typing import Optional
from urllib.parse import urlencode

from yammyquant.data.candle import Candle
from yammyquant.exchanges.base import Exchange, candle_from_records, jwt_hs256

# canonical interval -> Bithumb (Upbit-compatible) minute unit / non-minute path
_MINUTE_UNITS = {"1m": 1, "3m": 3, "5m": 5, "10m": 10, "15m": 15, "30m": 30,
                 "1h": 60, "4h": 240}
_NON_MINUTE = {"1d": "days", "1w": "weeks", "1M": "months"}


class BithumbExchange(Exchange):
    name = "bithumb"
    asset_class = "crypto"
    supports_trading = True
    BASE = "https://api.bithumb.com"

    def __init__(self, api_key: Optional[str] = None, secret_key: Optional[str] = None):
        # JWT "access_key" — kept as api_key to match the central config field name.
        self.api_key = api_key or os.getenv("BITHUMB_API_KEY")
        self.secret_key = secret_key or os.getenv("BITHUMB_SECRET_KEY")

    @staticmethod
    def _market(ticker: str) -> str:
        """Normalise to Bithumb market format ``KRW-BTC``.

        Accepts ``KRW-BTC`` / ``BTC`` / ``BTC_KRW`` / ``BTC/KRW`` (defaults the
        payment currency to KRW when only the base asset is given).
        """
        t = ticker.upper().replace("/", "-").replace("_", "-")
        if "-" not in t:
            return f"KRW-{t}"
        a, b = t.split("-", 1)
        quotes = ("KRW", "USDT")
        if a in quotes:
            return t                  # already quote-first (KRW-BTC)
        if b in quotes:
            return f"{b}-{a}"         # base-first (BTC-KRW) -> flip
        return t                      # crypto-crypto pair, leave as given

    # -- market data -------------------------------------------------------
    def read(self, ticker: str, interval: str = "1d", count: int = 200,
             start=None, end=None) -> Candle:
        market = self._market(ticker)
        path, params = self._candle_request(market, interval, count, end)
        raw = self._request("GET", self.BASE + path, params=params)
        return self._parse_candles(market, interval, raw)

    @staticmethod
    def _candle_request(market: str, interval: str, count: int, end) -> tuple[str, dict]:
        params: dict = {"market": market, "count": min(count, 200)}
        if end is not None:
            params["to"] = end if isinstance(end, str) else end.strftime("%Y-%m-%d %H:%M:%S")
        if interval in _MINUTE_UNITS:
            return f"/v1/candles/minutes/{_MINUTE_UNITS[interval]}", params
        if interval in _NON_MINUTE:
            return f"/v1/candles/{_NON_MINUTE[interval]}", params
        raise ValueError(f"unsupported Bithumb interval {interval!r}")

    @staticmethod
    def _parse_candles(market: str, interval: str, raw: list) -> Candle:
        records = [
            {"time": r["candle_date_time_kst"], "open": r["opening_price"],
             "high": r["high_price"], "low": r["low_price"],
             "close": r["trade_price"], "volume": r["candle_acc_trade_volume"]}
            for r in raw
        ]
        return candle_from_records(market.replace("-", ""), interval, records)

    # -- auth (JWT HS256, Upbit-compatible) --------------------------------
    def _auth_headers(self, params: Optional[dict] = None) -> dict:
        if not self.api_key or not self.secret_key:
            raise RuntimeError("Bithumb API keys required (BITHUMB_API_KEY / BITHUMB_SECRET_KEY)")
        payload = {"access_key": self.api_key, "nonce": str(uuid.uuid4())}
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
        params = {"market": self._market(ticker),
                  "side": "bid" if side.upper() == "BUY" else "ask"}
        if order_type == "limit":
            params.update(volume=str(quantity), price=str(price), ord_type="limit")
        elif order_type == "market":
            if side.upper() == "BUY":   # market-buy is by total KRW (price)
                params.update(price=str(price), ord_type="price")
            else:
                params.update(volume=str(quantity), ord_type="market")
        else:
            raise ValueError(f"unsupported order_type {order_type!r}")
        return self._request("POST", self.BASE + "/v1/orders",
                             headers=self._auth_headers(params), json_body=params)

    def order_status(self, order_id: str, ticker: str) -> dict:
        params = {"uuid": order_id}
        return self._request("GET", self.BASE + "/v1/order",
                             headers=self._auth_headers(params), params=params)
