"""Common exchange-adapter interface and shared crypto/HTTP helpers."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Optional

import pandas as pd

from yammyquant.data.candle import Candle, OHLCV_COLUMNS


def _b64url(raw: bytes) -> bytes:
    return base64.urlsafe_b64encode(raw).rstrip(b"=")


def jwt_hs256(payload: dict, secret: str) -> str:
    """Encode a JWT (HS256) using only stdlib — Upbit/Bithumb-v1 style auth.

    Avoids a PyJWT/``cryptography`` dependency, which keeps the install light and
    sidesteps native-build issues.
    """
    header = _b64url(json.dumps({"alg": "HS256", "typ": "JWT"}, separators=(",", ":")).encode())
    body = _b64url(json.dumps(payload, separators=(",", ":")).encode())
    signing_input = header + b"." + body
    sig = hmac.new(secret.encode(), signing_input, hashlib.sha256).digest()
    return (signing_input + b"." + _b64url(sig)).decode()


def candle_from_records(ticker: str, interval: str, records: list[dict]) -> Candle:
    """Build a :class:`Candle` from a list of {time, open, high, low, close, volume}."""
    df = pd.DataFrame.from_records(records)
    if df.empty:
        df = pd.DataFrame(columns=["time", *OHLCV_COLUMNS])
    df["time"] = pd.to_datetime(df["time"])
    df = df.set_index("time").sort_index()
    df = df[~df.index.duplicated(keep="last")]
    return Candle(ticker, df[list(OHLCV_COLUMNS)].astype(float), interval=interval)


class Exchange(ABC):
    """A venue adapter: candle data + (optionally) balances and orders."""

    name: str = "exchange"
    asset_class: str = "crypto"   # or "stock"
    supports_trading: bool = False

    @abstractmethod
    def read(
        self,
        ticker: str,
        interval: str = "1d",
        count: int = 200,
        start: Optional[datetime | str] = None,
        end: Optional[datetime | str] = None,
    ) -> Candle:
        """Fetch OHLCV candles as a :class:`Candle`."""

    def balances(self) -> dict:
        raise NotImplementedError(f"{self.name} adapter does not implement balances()")

    def create_order(self, ticker: str, side: str, quantity: float,
                     price: Optional[float] = None, order_type: str = "limit") -> dict:
        raise NotImplementedError(f"{self.name} adapter does not implement create_order()")

    # -- HTTP (overridable / mockable in tests) ----------------------------
    def _request(self, method: str, url: str, headers: Optional[dict] = None,
                 params: Optional[dict] = None, json_body: Optional[dict] = None,
                 data: Optional[dict] = None) -> dict:
        import requests  # optional dependency

        resp = requests.request(method, url, headers=headers, params=params,
                                json=json_body, data=data, timeout=15)
        resp.raise_for_status()
        return resp.json()


def hmac_sha512_hex(secret: str, message: str) -> str:
    return hmac.new(secret.encode(), message.encode(), hashlib.sha512).hexdigest()


def hmac_sha256_hex(secret: str, message: str) -> str:
    return hmac.new(secret.encode(), message.encode(), hashlib.sha256).hexdigest()


def pick(row: dict, names: tuple[str, ...]):
    """Return the first present, non-null value among ``names`` (field aliases)."""
    for n in names:
        if n in row and row[n] is not None:
            return row[n]
    raise KeyError(f"none of {names} present in row {list(row)}")
