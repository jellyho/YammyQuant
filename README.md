# YammyQuant

An **agentic quant research cockpit**. Claude Code is the operator — it drives a
CLI toolbelt over the `yammyquant` library to collect data, backtest, train RL
agents, generate signals, and manage a paper/live portfolio. A web **dashboard**
(FastAPI + a dependency-free SPA) lets you watch everything live and leave the
operator instructions.

No paid LLM API in the loop — the brain is your Claude Code session. The
dashboard is the cockpit; the conversation happens in Claude Code.

```
Claude Code (operator)  ──drives──▶  yq CLI toolbelt
        │                                │
        │  reads instructions            │ writes state + logs activity
        ▼                                ▼
   ┌──────────────────  shared state  ──────────────────┐
   │  SQLite (positions, trades, equity, signals,        │
   │  activity log, instruction inbox) + DuckDB candles  │
   └──────────────────────────┬──────────────────────────┘
                              ▼
              FastAPI cockpit + SPA dashboard
       (charts · positions · trade approvals · inbox)
```

## Install

```bash
pip install -e '.[all]'        # everything
pip install -e '.[web]'        # just the dashboard
pip install -e '.[binance]'    # Binance data/trading
```

## Quickstart

```bash
# 1. collect some candles (needs network; or seed your own — see examples/)
yq collect BTCUSDT 1d 1h

# 2. research
yq features BTCUSDT 1d                       # returns, vol, volume z-score, RSI, ...
yq backtest BTCUSDT 1d macross --fast 5 --slow 20
yq optimize BTCUSDT 1d macross --walk-forward 4   # grid search + out-of-sample
yq scan BTCUSDT ETHUSDT --interval 1d --strategy donchian_breakout
yq strategies --disable rsi_reversion       # list / toggle (mirrors the dashboard)
yq train BTCUSDT 1d --timesteps 50000        # train an RL agent (needs .[rl])

# 3. operate the account
yq watch add BTCUSDT --interval 1d           # watchlist = the universe for cycles
yq risk set max_open_positions=5 daily_loss_limit=200   # enforced on every order
yq trade BTCUSDT BUY 0.1 --price 65000 --mode paper     # paper fills; live queues
yq cycle                                     # refresh → scan → mark → notify (one pass)
yq schedule --interval 300                   # keep it running between sessions
yq report          # realized PnL, drawdown, per-symbol     yq doctor   # health check

# 4. launch the cockpit
yq dashboard          # → http://127.0.0.1:8000
```

In the dashboard you can watch the price/equity charts, approve or reject
pending trades, close positions, and **leave instructions** for the operator —
which Claude Code reads with `yq inbox` on its next run.

## The library

The CLI is a thin layer over a clean, tested Python framework you can also use
directly:

```python
from yammyquant import Candle, Backtest, MACross
result = Backtest(candle, MACross(5, 20), cash=10_000, fee=0.001).run()
print(result)            # Sharpe, max drawdown, win rate, profit factor, ...
```

- **`data/`** — typed `Candle` + dependency-free indicators (sma/ema/rsi/atr/
  bbands/macd), DuckDB+Parquet store, Binance source, and a **feature pipeline**
  (`features.py`: returns, realized vol, volume z-score, RSI, trend, ATR%).
- **`backtest/`** — order/portfolio/broker/engine with fees & slippage; a **risk
  layer** (`RiskConfig`: position sizing, stop-loss/take-profit, drawdown
  kill-switch); **optimization** (`grid_search`, `walk_forward`); and metrics
  (Sharpe, Sortino, Calmar, max drawdown, CAGR, volatility, win rate, profit
  factor, trade stats).
- **`strategy/`** — `Strategy` base + built-ins (`MACross`, `VolatilityBreakout`,
  `RSIReversion`, `DonchianBreakout`); toggle on/off from the cockpit.
- **`data/sources/`** — DuckDB+Parquet store, Binance source, and `CCXTSource`
  for 100+ exchanges.
- **`exchanges/`** — native per-exchange adapters (data + balances + orders):
  **Binance, Upbit, Bithumb, Coinone, Korbit** (crypto) & **KIS/한국투자증권**,
  **Toss/토스증권** (KR stocks), plus any **ccxt** venue — all configured in one
  place via `yq config`. See [`docs/EXCHANGES.md`](docs/EXCHANGES.md).
- **`rl/`** — `ChartFollowingEnv` (Gymnasium) for RL experiments.
- **`state/`** + **`ops/`** + **`web/`** — the cockpit (shared state, toolbelt, dashboard).

## How it compares

See [`docs/BENCHMARK.md`](docs/BENCHMARK.md) for a feature-by-feature comparison
against freqtrade, Jesse, NautilusTrader, FinRL, and the LLM-agent repos
(ai-hedge-fund, TradingAgents, FinRobot). Short version: YammyQuant now ships the
risk layer, optimization/walk-forward, expanded analytics, and multi-exchange
data those frameworks have — and its agentic operator is your Claude Code
session, so it needs **no paid LLM API**.

## Money safety

Paper trading is the default. **Live orders require both** `YQ_ALLOW_LIVE=1`
**and** explicit human approval (a dashboard button or `yq approve <id>`). Without
the flag, an approved live order is rejected. Binance keys are read from
`BINANCE_API_KEY` / `BINANCE_SECRET_KEY` (environment only — never hardcoded).

## For Claude Code

See [`CLAUDE.md`](CLAUDE.md) for the operator workflow (read the inbox, run the
toolbelt, record trades).

## Development

```bash
pip install -e '.[all,dev]'
pytest -q          # 118 tests
python examples/backtest_synthetic.py
```
