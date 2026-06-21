# Money safety

!!! danger "Live trading has two hard gates"
    A live order executes only with **(1)** the env flag `YQ_ALLOW_LIVE=1` **and
    (2)** explicit human approval (a dashboard button or `yq approve <id>`).
    Without the flag, an approved live order is rejected. The operator never sets
    that flag — it's the user's call.

## Paper by default

Paper trades fill immediately against a simulated book. This is the default mode
for `yq trade` and `yq decide`, so you can run the whole loop — collect, scan,
decide, mark, report — without any real money at risk.

Paper is built to **mirror live**, not flatter it: paper orders fill at the
exchange's **real-time price** (omit `--price` and it uses the live quote), pay
that venue's **real maker/taker fees**, and incur a configurable **slippage**
(`yq settings slippage=0.001`). So the intended pipeline — *backtest → paper →
live* — costs the same at every stage, and a strategy that survives paper is a
sound live candidate.

## Live flow

```
yq trade SYM BUY 0.1 --mode live      # → status: pending (queued for approval)
        │
        ▼  human reviews in the dashboard (or CLI)
yq approve <id>                       # requires YQ_ALLOW_LIVE=1 in the env
        │
        ▼
order submitted → yq sync settles partial/filled live orders
```

## Auto mode (hands-off live, for AFK scalping)

Confirming every order is impractical for high-frequency intraday trading. **Auto
mode** lets live orders execute *without* the per-order approval — but it does
**not** remove the other protections. It is armed only when **all** of these hold:

| Gate | Who sets it | Purpose |
|---|---|---|
| `YQ_ALLOW_LIVE=1` | you (env) | live trading is possible at all |
| `auto_approve=true` | you (`yq settings`) | skip the per-order approval queue |
| `trade_mode=live` + `auto_trade=true` | you (`yq settings`) | cycles place orders autonomously |

```bash
yq settings auto_trade=true trade_mode=live auto_approve=true
export YQ_ALLOW_LIVE=1        # your call, never set by the operator
```

Even when armed, **every order still passes the account risk policy** (`yq risk`)
— position caps, `daily_loss_limit`, cooldowns — which becomes your safety net
while unattended; a blocked order is rejected, not placed. Each auto-executed
fill is still **notified** (Discord/Slack), `yq cycle` reconciles the book against
the venue and settles resting orders every pass, and a failed placement is marked
rejected rather than left dangling. `yq doctor` reports `auto_live_armed` and
flags it as an issue so the state is never a surprise.

**Kill-switch.** When today's realized loss hits the `daily_loss_limit`, the next
`yq cycle` **auto-disarms** auto mode (`auto_approve` → off) and notifies you —
the loop stops opening new positions for you and waits for a conscious re-arm,
rather than re-attempting rejected entries all day. Exits keep working (sells are
never gated). Turn auto mode off any time with `yq settings auto_approve=false`,
or from the **Auto mode** card in the dashboard (a toggle plus a live armed badge).

!!! warning "Auto mode places real orders with no human in the loop"
    Only arm it once a strategy has earned it — validate in backtest, confirm in
    paper (`yq promote`), set tight `yq risk` guardrails, then enable. The
    operator never sets `YQ_ALLOW_LIVE` or `auto_approve` for you.

## Credentials

- Binance keys come from `BINANCE_API_KEY` / `BINANCE_SECRET_KEY` (environment
  only — never hardcoded, never committed).
- All other exchange keys/options are set in one place via `yq config set
  <exchange> field=value` (resolving override → config file → env). See
  [Exchanges](EXCHANGES.md).

## Notifications

A Discord webhook (`DISCORD_WEBHOOK_URL`) and/or Slack (`SLACK_WEBHOOK_URL`) fire
— send a custom message or a status digest any time with `yq notify` /
`yq notify --status` — when a live order needs approval,
a risk rejection happens, or a cycle finds signals — so you stay in the loop while
the operator runs unattended.
