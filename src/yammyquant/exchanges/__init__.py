"""Native per-exchange API adapters with one central configuration.

Each adapter implements the :class:`Exchange` interface — candle data plus
(where supported) balances and order placement. Everything is configured in one
place (:mod:`yammyquant.exchanges.config`): credentials/options resolve from a
central config file or environment variables, so you never edit an adapter file
to set keys. Use :func:`get_exchange` to obtain a fully-configured adapter.

Coverage
--------
- **Crypto (native):** Binance, Upbit, Bithumb, Coinone, Korbit
- **Korean stocks (native):** 한국투자증권 (KIS), 토스증권 (Toss)
- **Anything else:** any ccxt exchange id (Bybit, OKX, Coinbase, Kraken, …)

.. note::
   Candle parsing, auth signing, request building, and config resolution are
   unit-tested with mocks; live network calls need API keys and follow each
   venue's published docs — verify before trading real funds. For Coinone/Korbit
   the public candles are native and authenticated orders delegate to ccxt; for
   Toss, confirm the request paths against the developer portal.
"""

from yammyquant.exchanges.base import Exchange, jwt_hs256
from yammyquant.exchanges.binance import BinanceExchange
from yammyquant.exchanges.upbit import UpbitExchange
from yammyquant.exchanges.bithumb import BithumbExchange
from yammyquant.exchanges.coinone import CoinoneExchange
from yammyquant.exchanges.korbit import KorbitExchange
from yammyquant.exchanges.korea_investment import KoreaInvestment
from yammyquant.exchanges.toss import TossSecurities
from yammyquant.exchanges.config import (
    SPECS, ALIASES, build_exchange, describe, load_config, save_config,
    set_value, config_path, default_exchange,
)

# Back-compat: name -> adapter class for native venues (incl. aliases).
NATIVE = {name: spec.adapter for name, spec in SPECS.items() if spec.native}
NATIVE.update({alias: SPECS[target].adapter for alias, target in ALIASES.items()})


def get_exchange(name: str, **overrides) -> Exchange:
    """Return a centrally-configured exchange adapter by name."""
    return build_exchange(name, **overrides)


def list_exchanges() -> dict:
    """What's supported, grouped by asset class / how it's reached."""
    native_crypto = [n for n, s in SPECS.items() if s.native and s.asset_class == "crypto"]
    native_stock = [n for n, s in SPECS.items() if s.native and s.asset_class == "stock"]
    return {
        "native_crypto": native_crypto,
        "native_stock": native_stock,
        "via_ccxt": ["bybit", "okx", "coinbase", "kraken", "... any ccxt exchange id"],
        "config_file": str(config_path()),
        "default_exchange": default_exchange(),
    }


__all__ = [
    "Exchange", "jwt_hs256",
    "BinanceExchange", "UpbitExchange", "BithumbExchange", "CoinoneExchange",
    "KorbitExchange", "KoreaInvestment", "TossSecurities",
    "get_exchange", "list_exchanges", "describe", "NATIVE", "SPECS",
    "load_config", "save_config", "set_value", "config_path", "default_exchange",
]
