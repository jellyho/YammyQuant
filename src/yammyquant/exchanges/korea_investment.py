"""Korea Investment & Securities — KIS Developers REST API (Korean stocks).

The de-facto open API for Korean equities. Flow:
  1. Issue an OAuth access token (``/oauth2/tokenP``) from appkey/appsecret.
  2. Read daily/weekly/monthly candles
     (``/uapi/domestic-stock/v1/quotations/inquire-daily-itemchartprice``).
  3. Place a cash order (``/uapi/domestic-stock/v1/trading/order-cash``), whose
     body must be signed into a ``hashkey`` header.

Real vs. paper (모의투자) trading use different domains and ``tr_id`` codes.
Docs: https://apiportal.koreainvestment.com  ·  samples: github.com/koreainvestment/open-trading-api
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta
from typing import Optional

from yammyquant.data.candle import Candle
from yammyquant.exchanges.base import Exchange, candle_from_records

_REAL = "https://openapi.koreainvestment.com:9443"
_PAPER = "https://openapivts.koreainvestment.com:29443"
_PERIOD = {"1d": "D", "1w": "W", "1M": "M"}
# order-cash tr_id: (buy, sell) for real vs paper
_ORDER_TRID = {True: ("VTTC0802U", "VTTC0801U"), False: ("TTTC0802U", "TTTC0801U")}


class KoreaInvestment(Exchange):
    name = "kis"
    asset_class = "stock"
    supports_trading = True

    def __init__(self, appkey: Optional[str] = None, appsecret: Optional[str] = None,
                 account: Optional[str] = None, paper: bool = False):
        self.appkey = appkey or os.getenv("KIS_APPKEY")
        self.appsecret = appsecret or os.getenv("KIS_APPSECRET")
        # account number "12345678-01" → CANO + ACNT_PRDT_CD
        self.account = account or os.getenv("KIS_ACCOUNT", "")
        self.paper = paper
        self.base = _PAPER if paper else _REAL
        self._token: Optional[str] = None

    # -- auth --------------------------------------------------------------
    def token(self) -> str:
        if self._token:
            return self._token
        resp = self._request("POST", self.base + "/oauth2/tokenP", json_body={
            "grant_type": "client_credentials",
            "appkey": self.appkey, "appsecret": self.appsecret,
        })
        self._token = resp["access_token"]
        return self._token

    def _headers(self, tr_id: str, hashkey: Optional[str] = None) -> dict:
        h = {
            "content-type": "application/json; charset=utf-8",
            "authorization": f"Bearer {self.token()}",
            "appkey": self.appkey, "appsecret": self.appsecret, "tr_id": tr_id,
        }
        if hashkey:
            h["hashkey"] = hashkey
        return h

    def _hashkey(self, body: dict) -> str:
        resp = self._request("POST", self.base + "/uapi/hashkey", json_body=body, headers={
            "content-type": "application/json; charset=utf-8",
            "appkey": self.appkey, "appsecret": self.appsecret,
        })
        return resp["HASH"]

    # -- market data -------------------------------------------------------
    def read(self, ticker: str, interval: str = "1d", count: int = 100,
             start=None, end=None) -> Candle:
        """``ticker`` is a 6-digit code, e.g. ``"005930"`` (Samsung Electronics)."""
        if interval not in _PERIOD:
            raise ValueError(f"KIS supports daily/weekly/monthly only, got {interval!r}")
        end_dt = _as_dt(end) or datetime.now()
        start_dt = _as_dt(start) or (end_dt - timedelta(days=max(count, 100) * 2))
        params = {
            "FID_COND_MRKT_DIV_CODE": "J", "FID_INPUT_ISCD": ticker,
            "FID_INPUT_DATE_1": start_dt.strftime("%Y%m%d"),
            "FID_INPUT_DATE_2": end_dt.strftime("%Y%m%d"),
            "FID_PERIOD_DIV_CODE": _PERIOD[interval], "FID_ORG_ADJ_PRC": "0",
        }
        raw = self._request(
            "GET", self.base + "/uapi/domestic-stock/v1/quotations/inquire-daily-itemchartprice",
            headers=self._headers("FHKST03010100"), params=params,
        )
        return self._parse_candles(ticker, interval, raw)

    @staticmethod
    def _parse_candles(ticker: str, interval: str, raw: dict) -> Candle:
        records = [
            {"time": datetime.strptime(r["stck_bsop_date"], "%Y%m%d"),
             "open": r["stck_oprc"], "high": r["stck_hgpr"], "low": r["stck_lwpr"],
             "close": r["stck_clpr"], "volume": r["acml_vol"]}
            for r in raw.get("output2", []) if r.get("stck_bsop_date")
        ]
        return candle_from_records(ticker, interval, records)

    # -- trading -----------------------------------------------------------
    def balances(self) -> dict:
        cano, prdt = self._account_parts()
        tr_id = "VTTC8434R" if self.paper else "TTTC8434R"
        params = {"CANO": cano, "ACNT_PRDT_CD": prdt, "AFHR_FLPR_YN": "N",
                  "OFL_YN": "", "INQR_DVSN": "02", "UNPR_DVSN": "01",
                  "FUND_STTL_ICLD_YN": "N", "FNCG_AMT_AUTO_RDPT_YN": "N",
                  "PRCS_DVSN": "01", "CTX_AREA_FK100": "", "CTX_AREA_NK100": ""}
        return self._request(
            "GET", self.base + "/uapi/domestic-stock/v1/trading/inquire-balance",
            headers=self._headers(tr_id), params=params)

    def create_order(self, ticker: str, side: str, quantity: float,
                     price: Optional[float] = None, order_type: str = "limit") -> dict:
        cano, prdt = self._account_parts()
        buy_trid, sell_trid = _ORDER_TRID[self.paper]
        tr_id = buy_trid if side.upper() == "BUY" else sell_trid
        body = {
            "CANO": cano, "ACNT_PRDT_CD": prdt, "PDNO": ticker,
            "ORD_DVSN": "01" if order_type == "market" else "00",  # 01=시장가 00=지정가
            "ORD_QTY": str(int(quantity)),
            "ORD_UNPR": "0" if order_type == "market" else str(int(price or 0)),
        }
        headers = self._headers(tr_id, hashkey=self._hashkey(body))
        return self._request(
            "POST", self.base + "/uapi/domestic-stock/v1/trading/order-cash",
            headers=headers, json_body=body)

    def fundamentals(self, ticker: str) -> dict:
        """Current price + key valuation ratios (PER/PBR/EPS/BPS) for a stock."""
        raw = self._request(
            "GET", self.base + "/uapi/domestic-stock/v1/quotations/inquire-price",
            headers=self._headers("FHKST01010100"),
            params={"FID_COND_MRKT_DIV_CODE": "J", "FID_INPUT_ISCD": ticker})
        out = raw.get("output", {})
        pick = lambda k: float(out[k]) if out.get(k) not in (None, "") else None
        return {"ticker": ticker, "price": pick("stck_prpr"), "per": pick("per"),
                "pbr": pick("pbr"), "eps": pick("eps"), "bps": pick("bps"),
                "market_cap": pick("hts_avls"), "week52_high": pick("w52_hgpr"),
                "week52_low": pick("w52_lwpr")}

    def _account_parts(self) -> tuple[str, str]:
        acct = self.account.replace("-", "")
        if len(acct) < 10:
            raise RuntimeError("KIS account required as '########-##' (KIS_ACCOUNT)")
        return acct[:8], acct[8:10]


def _as_dt(value) -> Optional[datetime]:
    if value is None or isinstance(value, datetime):
        return value
    return datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
