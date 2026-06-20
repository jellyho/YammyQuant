# The toolbelt (`yq`)

Everything the operator does runs through one CLI. Every command logs to shared
state, so the dashboard reflects it live.

## Data & research

| Command | What it does |
|---|---|
| `yq collect SYM 1d 1h` | Backfill candles → DuckDB store (`--exchange` for venue). |
| `yq features SYM 1d` | Compute & store candle-derived features. |
| `yq backtest SYM 1d macross --fast 5 --slow 20` | Run a strategy; Sharpe / drawdown / win rate. |
| `yq optimize SYM 1d macross --metric sharpe` | Grid search over parameters. |
| `yq optimize SYM 1d macross --walk-forward 4` | Out-of-sample (walk-forward) validation. |
| `yq scan A B --interval 1d --strategy donchian_breakout` | Emit signals across symbols. |
| `yq train SYM 1d --timesteps 50000` | Train an RL agent (needs `.[rl]`). |

## Information

| Command | What it does |
|---|---|
| `yq news --collect` | Pull RSS headlines, tag watchlist, score sentiment. |
| `yq news SYM` | List stored news for a symbol (you judge it). |
| `yq brief SYM --exchange kis` | Research digest: price + features + news + fundamentals. |
| `yq disclosures CORP --symbol SYM` | DART (전자공시) filings (needs `DART_API_KEY`). |

See [Information layer](information-layer.md) for the full picture.

## Operating the account

| Command | What it does |
|---|---|
| `yq watch add SYM --interval 1d` | Watchlist — the universe for cycles. |
| `yq decide --weight 0.1` | Signals → risk-sized orders (dry-run). |
| `yq decide --weight 0.1 --execute` | …actually submit (paper; `--mode live` queues). |
| `yq target BTCUSDT=0.5 ETHUSDT=0.3` | Set portfolio target weights. |
| `yq target --risk-parity A B C` | Auto-set inverse-volatility (risk-parity) weights. |
| `yq rebalance --execute` | Move holdings toward targets. |
| `yq trade SYM BUY 0.1 --price 65000 --mode paper` | Paper fills now. |
| `yq approve N` / `yq reject N` | Act on a pending live trade. |
| `yq mark` / `yq sync` | Mark to market / settle live orders. |
| `yq cycle` | One maintenance pass: refresh → scan → mark → notify. |
| `yq schedule --interval 300` | Run cycles forever (or cron `yq cycle`). |
| `yq risk set max_open_positions=5 daily_loss_limit=200` | Account risk guardrails. |

## Memory & introspection

| Command | What it does |
|---|---|
| `yq recall [query]` | Session-start memory: ranked journal + inbox + positions. |
| `yq journal "…" --tag thesis --importance 8` | Cross-session memory note. |
| `yq expect SYM 1d macross` | Record a backtest baseline. |
| `yq decay` | Realized vs baseline (strategy-decay alert). |
| `yq report` | Realized PnL, drawdown, per-symbol. |
| `yq attribution` | Per-strategy PnL attribution (closed round-trips). |
| `yq portfolio A B C --strategy macross [--risk-parity]` | Multi-symbol portfolio backtest (equal or inverse-vol weights). |
| `yq correlate A B C` | Return-correlation matrix (diversification check). |
| `yq reconcile` | Local positions vs exchange balances. |
| `yq doctor` | Data freshness / config / account health. |
| `yq status` | Full cockpit state snapshot (JSON). |
| `yq dashboard` | Launch the cockpit web app. |

See [Memory & persistence](memory.md) for how `recall` ranks notes.

## Self-improvement & alerts

| Command | What it does |
|---|---|
| `yq new strategy\|indicator\|skill <name>` | Scaffold your own, auto-loaded (see [Self-improvement](self-improvement.md)). |
| `yq plugins` | List operator-authored plugins + any load errors. |
| `yq notify "msg"` | Push a message to Discord/Slack. |
| `yq notify --status` | Push a status digest (equity, PnL, positions, pending). |
