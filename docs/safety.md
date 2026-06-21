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
