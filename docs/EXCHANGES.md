# Exchange support

YammyQuant talks to exchanges through a single `Exchange` adapter interface
(`yammyquant/exchanges/`): **candle data** plus, where supported, **balances**
and **order placement**. Get one with `get_exchange(name, **creds)`.

```python
from yammyquant.exchanges import get_exchange

up = get_exchange("upbit")                 # keys from env (UPBIT_ACCESS_KEY/SECRET)
candle = up.read("KRW-BTC", "1d", count=200)
# up.balances(); up.create_order("KRW-BTC", "BUY", 0.01, price=50_000_000)
```

From the toolbelt:

```bash
yq exchanges                                  # list what's supported
yq collect 005930 1d --exchange kis           # Samsung Elec. daily via KIS
yq collect KRW-BTC 1d 1h --exchange upbit
```

## Coverage

| Exchange | Adapter | Class | Auth | Data | Trade | Notes |
| --- | --- | --- | --- | :-: | :-: | --- |
| **Upbit** (업비트) | `upbit` | crypto | JWT HS256 + SHA512 query hash | ✅ | ✅ | `KRW-BTC` market format |
| **Bithumb** (빗썸) | `bithumb` | crypto | HMAC-SHA512 (classic API) | ✅ | ✅ | `BTC` / `BTC_KRW` |
| **한국투자증권** (KIS) | `kis` | stock | OAuth2 token + hashkey | ✅ | ✅ | 6-digit codes; real & paper(모의) domains |
| **토스증권** (Toss) | `toss` | stock | OAuth2 bearer | ⚠️ | ⚠️ | 2026 Open API; **confirm paths** (see below) |
| Binance / Bybit / OKX / Coinbase / Kraken / Coinone / Korbit / … | `<ccxt id>` | crypto | per ccxt | ✅ | ✅ | via `[ccxt]`; 100+ venues |

Binance also has a native resumable backfill used by `yq collect … --exchange binance`
(the default), built on `data/sources/binance.py`.

## Credentials (environment only — never hardcode)

| Exchange | Env vars |
| --- | --- |
| Upbit | `UPBIT_ACCESS_KEY`, `UPBIT_SECRET_KEY` |
| Bithumb | `BITHUMB_API_KEY`, `BITHUMB_SECRET_KEY` |
| KIS | `KIS_APPKEY`, `KIS_APPSECRET`, `KIS_ACCOUNT` (`########-##`) |
| Toss | `TOSS_APP_KEY`, `TOSS_APP_SECRET`, `TOSS_ACCOUNT`, optional `TOSS_BASE_URL` |
| Binance | `BINANCE_API_KEY`, `BINANCE_SECRET_KEY` |
| ccxt venue `X` | `X_API_KEY`, `X_SECRET_KEY` |

Live orders still pass through YammyQuant's money-safety gates: `YQ_ALLOW_LIVE=1`
**and** explicit approval. The configured live venue is the `exchange` setting in
the cockpit state (default `binance`).

## ⚠️ Toss Securities — finish-the-adapter note

Toss Securities launched an OAuth2 REST Open API in 2026 (KRX + US stocks: market
data, account, orders), in staged rollout for pre-applicants
([apply](https://corp.tossinvest.com/ko/open-api) · [docs](https://developers.tossinvest.com/docs)).
The exact request paths live behind the developer portal, so the `*_PATH`
constants in `exchanges/toss.py` are **placeholders to confirm** against the
official spec once your application is approved. The OAuth2 token flow, bearer
auth, candle parsing (tolerant of field-name aliases), and order building are
implemented and unit-tested with mocks — set `TOSS_BASE_URL` / update the path
constants to match the published docs and it's live.

## Verification status

Candle parsing, JWT/HMAC signing, request building, and registry wiring are
unit-tested (`tests/test_exchanges.py`). Live network calls require API keys and
are implemented to each venue's published spec — verify against current official
docs before trading real funds.
