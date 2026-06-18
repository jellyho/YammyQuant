# YammyQuant — operator guide (for Claude Code)

You (Claude Code) are the **operator** of this quant platform. There is no paid
LLM API in the loop — *you* are the brain. You drive a CLI toolbelt over the
`yammyquant` library to collect data, backtest, train, generate signals, and
manage a paper/live portfolio. A FastAPI **cockpit** dashboard lets the user
watch everything live and leave you instructions.

## The loop

1. **Read the inbox first** every session — the user leaves instructions there
   from the dashboard:
   ```bash
   yq inbox            # show unread instructions
   yq inbox --mark-read
   ```
2. **Do the work** with the toolbelt (below). Every command logs to the shared
   state, so the dashboard reflects what you did in real time.
3. **Record decisions** as trades (paper by default). Live orders queue for the
   user's approval in the dashboard.

## Toolbelt (`yq`)

```bash
yq exchanges                        # list supported exchanges (KR + foreign)
yq collect BTCUSDT 1d 1h            # backfill candles from Binance → DuckDB store
yq collect KRW-BTC 1d --exchange upbit       # or upbit/bithumb/kis/toss/<ccxt id>
yq collect 005930 1d --exchange kis          # Korean stock (한국투자증권)
yq features BTCUSDT 1d              # compute & store candle-derived features
yq backtest BTCUSDT 1d macross --fast 5 --slow 20
yq optimize BTCUSDT 1d macross --metric sharpe          # grid search
yq optimize BTCUSDT 1d macross --walk-forward 4         # out-of-sample validation
yq scan BTCUSDT ETHUSDT --interval 1d --strategy donchian_breakout   # emit signals
yq strategies --disable rsi_reversion   # list / toggle strategies
yq train BTCUSDT 1d --timesteps 50000   # train an RL agent (needs .[rl])
yq trade BTCUSDT BUY 0.1 --price 65000 --mode paper        # paper fills now
yq trade BTCUSDT BUY 0.1 --price 65000 --mode live         # live → pending approval
yq approve 7        # approve a pending trade   yq reject 7

# operating the account
yq watch add BTCUSDT --interval 1d         # watchlist (universe for cycles)
yq decide --weight 0.1                      # signals → risk-sized orders (dry-run)
yq decide --weight 0.1 --execute            # ...actually submit (paper; --mode live to queue)
yq decide --execute --type limit            # limit orders (live ones rest until synced)
yq target BTCUSDT=0.5 ETHUSDT=0.3           # set portfolio target weights
yq rebalance --execute                      # move holdings toward targets
yq expect BTCUSDT 1d macross               # record a backtest baseline
yq decay                                    # realized vs baseline (strategy-decay alert)
yq mark                                     # mark positions to market (live price)
yq sync                                     # poll & settle submitted/partial live orders
yq cycle                                    # one maintenance cycle: refresh→scan→mark→notify
yq schedule --interval 300                  # run cycles forever (or cron `yq cycle`)
yq risk set max_open_positions=5 daily_loss_limit=200   # account risk guardrails
yq report                                   # realized PnL, drawdown, per-symbol
yq reconcile                                # local positions vs exchange balances
yq doctor                                   # data freshness / config / account health
yq journal "why I entered BTC ..." --tag thesis   # cross-session memory
yq status           # full cockpit state snapshot (JSON)
yq dashboard        # launch the cockpit web app (http://127.0.0.1:8000)
```

**Signal → order.** `yq decide` aggregates enabled-strategy signals per watchlist
symbol into concrete, risk-sized orders (entry sized to a fraction of equity;
exits flatten). Dry-run by default; `--execute` submits; `--type limit` rests
live orders until `yq sync` settles them (handles partial fills). Set
`auto_trade=true` (state setting) to have `yq cycle` / the scheduler call
`decide --execute` automatically (paper unless `trade_mode=live`).

**Portfolio & decay.** `yq target`/`yq rebalance` maintain target weights across
holdings. `yq expect` records a backtest baseline; `yq decay` warns when realized
performance falls below it (out-of-sample edge erosion).

**Operating loop & safety.** The account-level **risk policy** (`yq risk`) is
enforced on every order (paper + live) — it can reject a trade before it fills.
**Notifications** (Discord webhook via `DISCORD_WEBHOOK_URL`) fire when a live
order needs approval, a risk rejection happens, or a cycle finds signals. Keep a
**journal** — you're ephemeral across sessions, so record why you entered/exited;
read it back next session. A **scheduler** (`yq schedule`, or cron + `yq cycle`)
keeps data fresh and signals current while you're away.

Strategies: `macross`, `volatility_breakout`, `rsi_reversion`, `donchian_breakout`.
Toggles set in the dashboard are read via `enabled_strategies(state)`.

Risk control is available on backtests via `Backtest(candle, strategy,
risk=RiskConfig(sizing="volatility", stop_loss=0.05, take_profit=0.1,
max_drawdown=0.2))`. See `docs/BENCHMARK.md` for how the toolbelt compares to
freqtrade / Jesse / nautilus / the LLM-agent repos and why our operator (you,
Claude Code) needs no paid API.

Exchanges (`yammyquant/exchanges/`, `get_exchange(name)`): native **Binance,
Upbit, Bithumb, Coinone, Korbit** (crypto) and **한국투자증권/KIS, 토스증권/Toss**
(KR stocks), plus any **ccxt** venue. All keys/options are configured in ONE
place — `yq config set <exchange> field=value` / `yq config show` — resolving
override → config file → env. Don't edit adapter files to set credentials. See
`docs/EXCHANGES.md` (Toss paths must be confirmed against its dev portal).

State lives in `yammyquant_state.db` (SQLite) and candles in `data_store/`
(DuckDB/Parquet). Both the CLI and the dashboard share them.

## Architecture

```
src/yammyquant/
├── data/        # Candle, indicators, DuckDB store, Binance source
├── backtest/    # order, portfolio, broker, engine, metrics
├── strategy/    # Strategy base + MACross / VolatilityBreakout
├── rl/          # gymnasium env (ChartFollowingEnv)
├── state/       # LiveState — shared SQLite cockpit state
├── ops/         # operator toolbelt: trading, operator fns, `yq` CLI
└── web/         # FastAPI cockpit + static SPA (Plotly, no build step)
```

When you write new strategies/collectors/trainers, expose them through `ops/`
so they show up in the cockpit and the CLI.

## Money safety (important)

- **Paper is the default.** Paper trades fill immediately against a simulated book.
- **Live trades never execute without two gates:** (1) env flag `YQ_ALLOW_LIVE=1`,
  and (2) explicit human approval (dashboard button or `yq approve`). Without the
  flag, an approved live trade is rejected. Never set `YQ_ALLOW_LIVE` yourself —
  that's the user's call.
- Binance keys come from `BINANCE_API_KEY` / `BINANCE_SECRET_KEY` (env only).

## Dev

```bash
pip install -e '.[all,dev]'
pytest -q
```
