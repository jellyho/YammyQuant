# Exchange support

YammyQuant talks to exchanges through one `Exchange` adapter interface
(`yammyquant/exchanges/`): **candle data** plus, where supported, **balances**
and **order placement**. Everything is configured in **one central place** — you
never edit an adapter file to set keys.

```python
from yammyquant.exchanges import get_exchange

up = get_exchange("upbit")                 # credentials resolved centrally
candle = up.read("KRW-BTC", "1d", count=200)
# up.balances(); up.create_order("KRW-BTC", "BUY", 0.01, price=50_000_000)
```

## Central configuration (no per-file editing)

All venue settings live in one JSON config file + environment variables, managed
with `yq config` — set keys, base URLs, account numbers, and the default venue in
one spot:

```bash
yq config show                                   # status of every exchange (masked)
yq config set upbit access_key=AK secret_key=SK  # write to the central file
yq config set kis appkey=.. appsecret=.. account=12345678-01 paper=true
yq config default upbit                          # default live venue
yq config path                                   # where the file lives
```

Resolution precedence per field: **explicit override → config file → environment
variable**. The file is searched at `$YAMMYQUANT_CONFIG`, then
`./yammyquant.config.json`, then `~/.config/yammyquant/config.json`. The single
source of truth for *what* each exchange needs is `SPECS` in
`exchanges/config.py`.

> The config file may hold secrets, so it's git-ignored. Prefer environment
> variables (or a secrets manager) for keys in shared/production setups.

## Coverage

| Exchange | Adapter | Class | Data | Trade | Notes |
| --- | --- | --- | :-: | :-: | --- |
| **Binance** | `binance` | crypto | ✅ native | ✅ native | `BTCUSDT`; resumable backfill |
| **Upbit** (업비트) | `upbit` | crypto | ✅ native | ✅ native | `KRW-BTC`; JWT auth |
| **Bithumb** (빗썸) | `bithumb` | crypto | ✅ native | ✅ native | `BTC`/`BTC_KRW`; HMAC-SHA512 |
| **Coinone** (코인원) | `coinone` | crypto | ✅ native | ⚙️ via ccxt | native public candles; orders via ccxt |
| **Korbit** (코빗) | `korbit` | crypto | ✅ native | ⚙️ via ccxt | native public candles; orders via ccxt |
| **한국투자증권** (KIS) | `kis` | stock | ✅ native | ✅ native | 6-digit codes; real & paper(모의) |
| **토스증권** (Toss) | `toss` | stock | ⚠️ | ⚠️ | 2026 Open API; **confirm paths** |
| Bybit / OKX / Coinbase / Kraken / … | `<ccxt id>` | crypto | ✅ | ✅ | via `[ccxt]`; 100+ venues |

> **토스뱅크(Toss Bank) ≠ 토스증권(Toss Securities).** Stock trading and its API
> belong to **Toss Securities** (the `toss` adapter). Toss Bank is the internet
> bank (deposits, loans, FX, open-banking transfers) and has **no stock-trading
> API**.

## Credentials (config keys / env vars)

| Exchange | Fields (config) | Env vars |
| --- | --- | --- |
| Binance | `api_key`, `secret_key` | `BINANCE_API_KEY`, `BINANCE_SECRET_KEY` |
| Upbit | `access_key`, `secret_key` | `UPBIT_ACCESS_KEY`, `UPBIT_SECRET_KEY` |
| Bithumb | `api_key`, `secret_key` | `BITHUMB_API_KEY`, `BITHUMB_SECRET_KEY` |
| Coinone | `api_key`, `secret_key` | `COINONE_API_KEY`, `COINONE_SECRET_KEY` |
| Korbit | `api_key`, `secret_key` | `KORBIT_API_KEY`, `KORBIT_SECRET_KEY` |
| KIS | `appkey`, `appsecret`, `account`, `paper` | `KIS_APPKEY`, `KIS_APPSECRET`, `KIS_ACCOUNT` |
| Toss | `app_key`, `app_secret`, `account`, `base_url`, `market` | `TOSS_APP_KEY`, `TOSS_APP_SECRET`, `TOSS_ACCOUNT`, `TOSS_BASE_URL` |
| ccxt venue `X` | `api_key`, `secret_key` | `X_API_KEY`, `X_SECRET_KEY` |

## From the toolbelt

```bash
yq exchanges                                  # list what's supported + config file path
yq collect 005930 1d --exchange kis           # Samsung Elec. daily via KIS
yq collect KRW-BTC 1d 1h --exchange upbit
```

Live orders still pass YammyQuant's money-safety gates (`YQ_ALLOW_LIVE=1` **and**
approval). The live venue is the cockpit `exchange` setting, else the central
`default_exchange`.

## ⚠️ Toss Securities — finish-the-adapter note

Toss Securities launched an OAuth2 REST Open API in 2026 (KRX + US: market data,
account, orders), in staged rollout for pre-applicants
([apply](https://corp.tossinvest.com/ko/open-api) · [docs](https://developers.tossinvest.com/docs)).
The exact request paths are behind the developer portal, so the `*_PATH`
constants in `exchanges/toss.py` are **placeholders to confirm**. The OAuth2
flow, bearer auth, candle parsing (alias-tolerant), and order building are
implemented and unit-tested with mocks — set `TOSS_BASE_URL` / update the paths
to match the published spec and it's live.

## Verification status

Candle parsing, JWT/HMAC signing, request building, central config resolution,
and registry wiring are unit-tested (`tests/test_exchanges.py`,
`tests/test_exchange_config.py`) with all HTTP mocked. Live network calls need
API keys and follow each venue's published spec — verify against current docs
before trading real funds (especially Toss paths and Coinone/Korbit order flows).
