"""Central exchange configuration — one place for every venue's settings.

Instead of editing a different adapter file (or hunting for the right env var)
per exchange, all of it is declared here and resolved through one factory:

* :data:`SPECS` — the single source of truth: each exchange's adapter, asset
  class, credential fields (with their env-var names), and non-secret options.
* a **central config file** (JSON) holds your keys/options for every exchange in
  one document; manage it with ``yq config`` (no file-by-file editing).
* :func:`build_exchange` resolves each value with precedence
  ``explicit override > config file > environment variable`` and constructs the
  adapter — so credentials live in one place and adapters stay dumb.

Config file search order (first found wins for reads):
  1. ``$YAMMYQUANT_CONFIG``
  2. ``./yammyquant.config.json``
  3. ``~/.config/yammyquant/config.json``
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from yammyquant.exchanges.binance import BinanceExchange
from yammyquant.exchanges.upbit import UpbitExchange
from yammyquant.exchanges.bithumb import BithumbExchange
from yammyquant.exchanges.coinone import CoinoneExchange
from yammyquant.exchanges.korbit import KorbitExchange
from yammyquant.exchanges.korea_investment import KoreaInvestment
from yammyquant.exchanges.toss import TossSecurities


@dataclass
class ExchangeSpec:
    adapter: type
    asset_class: str            # "crypto" | "stock"
    native: bool
    credentials: dict           # adapter kwarg -> ENV var name (secret values)
    options: dict = field(default_factory=dict)  # adapter kwarg -> default (non-secret)
    notes: str = ""


SPECS: dict[str, ExchangeSpec] = {
    "binance": ExchangeSpec(BinanceExchange, "crypto", True,
                            {"api_key": "BINANCE_API_KEY", "secret_key": "BINANCE_SECRET_KEY"},
                            notes="BTCUSDT format; resumable backfill via `yq collect`."),
    "upbit": ExchangeSpec(UpbitExchange, "crypto", True,
                          {"access_key": "UPBIT_ACCESS_KEY", "secret_key": "UPBIT_SECRET_KEY"},
                          notes="KRW-BTC market format."),
    "bithumb": ExchangeSpec(BithumbExchange, "crypto", True,
                            {"api_key": "BITHUMB_API_KEY", "secret_key": "BITHUMB_SECRET_KEY"}),
    "coinone": ExchangeSpec(CoinoneExchange, "crypto", True,
                            {"api_key": "COINONE_API_KEY", "secret_key": "COINONE_SECRET_KEY"},
                            notes="Native public candles; orders/balances via ccxt."),
    "korbit": ExchangeSpec(KorbitExchange, "crypto", True,
                           {"api_key": "KORBIT_API_KEY", "secret_key": "KORBIT_SECRET_KEY"},
                           notes="Native public candles; orders/balances via ccxt."),
    "kis": ExchangeSpec(KoreaInvestment, "stock", True,
                        {"appkey": "KIS_APPKEY", "appsecret": "KIS_APPSECRET",
                         "account": "KIS_ACCOUNT"},
                        options={"paper": False},
                        notes="한국투자증권. account as '########-##'; paper=모의투자."),
    "toss": ExchangeSpec(TossSecurities, "stock", True,
                         {"app_key": "TOSS_APP_KEY", "app_secret": "TOSS_APP_SECRET",
                          "account": "TOSS_ACCOUNT"},
                         options={"base_url": None, "market": "kr"},
                         notes="토스증권 2026 Open API; confirm paths against dev portal."),
}

ALIASES = {"korea_investment": "kis"}

# Catch-all credential pattern for any ccxt-backed exchange not in SPECS.
_CCXT_CREDS = {"api_key": "{NAME}_API_KEY", "secret_key": "{NAME}_SECRET_KEY"}


# -- config file -----------------------------------------------------------
def config_path(for_write: bool = False) -> Path:
    """Resolve the config file path (read: first existing; write: a writable default)."""
    candidates = [
        os.getenv("YAMMYQUANT_CONFIG"),
        "yammyquant.config.json",
        str(Path.home() / ".config" / "yammyquant" / "config.json"),
    ]
    candidates = [Path(c) for c in candidates if c]
    if not for_write:
        for c in candidates:
            if c.exists():
                return c
    return candidates[0] if os.getenv("YAMMYQUANT_CONFIG") else candidates[-1]


def load_config() -> dict:
    path = config_path()
    if path.exists():
        try:
            return json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def save_config(cfg: dict, path: Optional[Path] = None) -> Path:
    path = path or config_path(for_write=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cfg, indent=2, ensure_ascii=False))
    return path


def set_value(exchange: str, field_name: str, value, path: Optional[Path] = None) -> Path:
    """Set one exchange option/credential in the central config file."""
    cfg = load_config()
    cfg.setdefault("exchanges", {}).setdefault(exchange.lower(), {})[field_name] = value
    return save_config(cfg, path)


def default_exchange() -> str:
    return load_config().get("default_exchange") or os.getenv("YQ_EXCHANGE", "binance")


# -- resolution + factory --------------------------------------------------
def _canonical(name: str) -> str:
    return ALIASES.get(name.lower(), name.lower())


def _resolve(name: str, field_name: str, env_var: Optional[str], overrides: dict, ex_cfg: dict):
    if field_name in overrides and overrides[field_name] is not None:
        return overrides[field_name]
    if field_name in ex_cfg and ex_cfg[field_name] is not None:
        return ex_cfg[field_name]
    if env_var:
        return os.getenv(env_var)
    return None


def build_exchange(name: str, **overrides):
    """Construct an exchange adapter with centrally-resolved credentials/options."""
    key = _canonical(name)
    ex_cfg = load_config().get("exchanges", {}).get(key, {})
    spec = SPECS.get(key)

    if spec is None:  # ccxt fallback for any other venue id
        from yammyquant.exchanges.ccxt_adapter import CCXTExchange
        creds = {f: _resolve(key, f, env.format(NAME=key.upper()), overrides, ex_cfg)
                 for f, env in _CCXT_CREDS.items()}
        return CCXTExchange(key, **{k: v for k, v in creds.items() if v is not None})

    kwargs = {}
    for f, env in spec.credentials.items():
        val = _resolve(key, f, env, overrides, ex_cfg)
        if val is not None:
            kwargs[f] = val
    for f, default in spec.options.items():
        val = _resolve(key, f, None, overrides, ex_cfg)
        kwargs[f] = val if val is not None else default
        if kwargs[f] is None:
            del kwargs[f]
    return spec.adapter(**kwargs)


def describe() -> dict:
    """Human-readable status: per exchange, which fields are set and from where (masked)."""
    cfg = load_config()
    out = {"config_file": str(config_path()), "config_exists": config_path().exists(),
           "default_exchange": default_exchange(), "exchanges": {}}
    for name, spec in SPECS.items():
        ex_cfg = cfg.get("exchanges", {}).get(name, {})
        fields = {}
        for f, env in spec.credentials.items():
            if f in ex_cfg:
                fields[f] = "config:set"
            elif os.getenv(env):
                fields[f] = f"env:{env}"
            else:
                fields[f] = "missing"
        out["exchanges"][name] = {"asset_class": spec.asset_class, "native": spec.native,
                                  "credentials": fields, "notes": spec.notes}
    return out
