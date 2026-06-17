# Legacy code (pre-0.2 rewrite)

This directory holds the **original YammyQuant code**, kept for reference after
the 0.2 rewrite. It is no longer maintained and is not imported by the new
`yammyquant` package under `src/`.

The current framework lives in [`../src/yammyquant`](../src/yammyquant). See the
top-level [README](../README.md) for the new API.

## ⚠️ Security notice

Two secrets were hardcoded in this code and committed to git history:

- a Discord bot **token** (`utils/bot.py`)
- a MySQL **password** (`sql_chart_gui.py`)

The working-tree copies have been redacted to read from environment variables,
but **they remain in the git history** and must be treated as compromised:

- revoke/rotate the Discord bot token in the Discord developer portal,
- change the MySQL password.

## Mapping old → new

| Legacy | New |
| --- | --- |
| `data/core.py:Candle` | `yammyquant.data.candle.Candle` |
| `data/readers.py`, `data/updaters.py` (MySQL) | `yammyquant.data.sources.store.DuckDBStore`, `...binance.BinanceSource` |
| `trade/agents.py` (Agent) | `yammyquant.strategy` (Strategy) |
| `trade/core.py:Trader`, `envrionment/` | `yammyquant.backtest.engine.Backtest` |
| `trade/utils.py:Portfolio` | `yammyquant.backtest.portfolio.Portfolio` |
| `gym_env.py` (3 gym envs) | `yammyquant.rl.env.ChartFollowingEnv` (gymnasium) |
| `utils/bot.py` | `yammyquant.notify.discord.DiscordNotifier` |
