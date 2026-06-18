"""Native per-exchange API adapters.

Each adapter implements the :class:`Exchange` interface — candle data plus
(where supported) balances and order placement — against an exchange's own REST
API, rather than going through ccxt. This gives first-class support for venues
ccxt covers poorly, especially Korean ones.

Coverage
--------
- **Korean crypto:** Upbit, Bithumb  (``upbit``, ``bithumb``)
- **Korean stocks:** Korea Investment & Securities — KIS Developers (``kis``)
- **Everything else** (Binance, Bybit, OKX, Coinbase, Kraken, Coinone, Korbit, …):
  reached through ccxt via :class:`~yammyquant.exchanges.ccxt_adapter.CCXTExchange`.

Use :func:`get_exchange` to obtain an adapter by name.

.. note::
   The candle-parsing, auth-signing, and request-building logic is unit-tested
   with fixtures/mocks. Live network calls require API keys and are validated
   against each venue's official docs — verify against the current docs before
   trading real money.
"""

from yammyquant.exchanges.base import Exchange, jwt_hs256
from yammyquant.exchanges.upbit import UpbitExchange
from yammyquant.exchanges.bithumb import BithumbExchange
from yammyquant.exchanges.korea_investment import KoreaInvestment
from yammyquant.exchanges.toss import TossSecurities

NATIVE = {
    "upbit": UpbitExchange,
    "bithumb": BithumbExchange,
    "kis": KoreaInvestment,
    "korea_investment": KoreaInvestment,
    "toss": TossSecurities,
}


def get_exchange(name: str, **creds) -> Exchange:
    """Return an exchange adapter by name (native, else a ccxt-backed adapter)."""
    key = name.lower()
    if key in NATIVE:
        return NATIVE[key](**creds)
    from yammyquant.exchanges.ccxt_adapter import CCXTExchange
    return CCXTExchange(key, **creds)


def list_exchanges() -> dict:
    """What's supported, grouped by how it's reached."""
    return {
        "native_crypto": ["upbit", "bithumb"],
        "native_stock": ["kis (한국투자증권)", "toss (토스증권)"],
        "via_ccxt": ["binance", "bybit", "okx", "coinbase", "kraken",
                     "coinone", "korbit", "... any ccxt exchange id"],
    }


__all__ = [
    "Exchange",
    "jwt_hs256",
    "UpbitExchange",
    "BithumbExchange",
    "KoreaInvestment",
    "TossSecurities",
    "get_exchange",
    "list_exchanges",
]
