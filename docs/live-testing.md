# Live exchange testing

This walkthrough verifies that a venue's **live order path** —
`create_order` → `order_status` → `cancel_order` — actually works against your
real account, **before** you let a strategy trade real money.

!!! danger "These steps place real orders"
    YammyQuant's live adapters are exercised by unit tests with mocked HTTP, but
    each venue's real API must be confirmed against a real account. Use a
    **testnet** if the venue has one, otherwise the **smallest possible size**.
    The core of this guide is a *resting limit order far from the market* that
    rests unfilled and is then canceled — so you exercise the whole path with
    near-zero fill risk.

## 0. Prerequisites

- Paper-trade first (`yq cycle`, `yq report`) so you trust the loop itself.
- Have your API key/secret with **trading** permission (and, ideally, IP allow-listing).
- Know the venue's **minimum order size / notional** (e.g. Binance spot ≈ $5–10).

## 1. Configure credentials (no orders yet)

Keys live in the central config or environment — never in code, never committed.

```bash
yq exchanges                                  # what's supported
yq config set binance api_key=… secret_key=…  # or set BINANCE_API_KEY / BINANCE_SECRET_KEY
yq config show                                # masked — confirm the venue shows "set"
```

## 2. Read-only checks (still no orders)

Confirm market-data and authenticated reads work before placing anything.

```bash
yq collect BTCUSDT 1m --exchange binance   # public candles -> read() works
yq reconcile --exchange binance            # calls balances() -> auth read works
yq doctor                                  # config / freshness / account sanity
```

If `yq reconcile` returns your balances, authentication is good.

## 3. The safe smoke test — a resting limit that won't fill

Arrange a tiny **BUY limit far below** the market (it rests, never fills), then
cancel it. This exercises `create_order` → `order_status` → `cancel_order`.

```bash
export YQ_ALLOW_LIVE=1                      # your call — enables live placement

# tiny size, price ~50% below market so it cannot fill
yq trade BTCUSDT BUY 0.0001 --price 30000 --mode live --type limit --exchange binance
#   → status: pending  (#N, queued for approval)

yq approve N                                # places the real order at the venue
#   → status: submitted (resting, awaiting fill)

yq sync                                     # polls order_status — should stay open/submitted
yq status                                   # the open order is listed

yq cancel N --exchange binance              # cancels at the venue
#   → status: canceled
```

If the order appears at the venue (check the exchange UI too), `sync` reports it
open, and `cancel` removes it — the live path is verified. A `403`/auth error here
means the key lacks trading permission or IP allow-listing.

## 4. (Optional) a minimal real-fill round-trip

Only if you accept one real fill plus fees. Use the venue minimum.

```bash
yq trade BTCUSDT BUY <min_qty> --mode live --exchange binance   # market order
yq approve N                                                    # fills at the venue
yq reconcile --exchange binance --adopt-cash                    # local book == venue?
# flatten back out
yq trade BTCUSDT SELL <min_qty> --mode live --exchange binance
yq approve M
```

After this, confirm the **actual** fill was booked: `yq report` and the trade's
`meta.fill_price` / `fill_qty` / `fill_fee` should reflect what the venue charged,
not what you requested.

## 5. Reconcile & confirm the books match

```bash
yq reconcile --exchange binance      # `drift` empty, `cash_drift` null (or adopt it)
```

Position **and** cash drift should be clear. Investigate any mismatch before going further.

## 6. Per-venue notes

| Venue | Notes |
|---|---|
| **Binance** | Has a spot **testnet** — point the client at it via `yq config` and use test keys to rehearse §3–4 with zero risk. |
| **Upbit / Bithumb / Coinone / Korbit** | KRW pairs (`KRW-BTC`); small KRW minimums. Public candles are native; authenticated orders on Coinone/Korbit delegate to ccxt. |
| **KIS / Toss (KR stocks)** | Orders only during **market hours**. KIS offers a 모의투자 (paper) domain — prefer it for verification. **Toss request paths are unconfirmed** against its dev portal — confirm before any live order. |
| **ccxt venues** | `clientOrderId` (idempotency) support varies by exchange. |

## 7. Rollback & safety

- Cancel anything resting at any time: `yq cancel <id>` (or remote `flat` / `disarm` from Slack/Discord).
- Keep **auto mode off** during verification (`yq settings auto_approve=false`).
- Set risk guardrails before any unattended run: `yq risk set max_open_positions=… max_order_value=… daily_loss_limit=…`.
- Live always needs **`YQ_ALLOW_LIVE=1`** *and* approval (or, deliberately, auto mode). See [Money safety](safety.md).

Once §3 passes on every venue you'll use — and §4 if you want fill-path
confidence — the live integration is verified and you can graduate a
paper-validated strategy with `yq promote`.
