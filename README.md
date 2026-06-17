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
yq backtest BTCUSDT 1d macross --fast 5 --slow 20
yq scan BTCUSDT ETHUSDT --interval 1d --strategy macross

# 3. trade (paper fills immediately; live queues for approval)
yq trade BTCUSDT BUY 0.1 --price 65000 --mode paper

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
  bbands/macd), DuckDB+Parquet store, Binance source.
- **`backtest/`** — order/portfolio/broker/engine with fees, slippage, equity
  curve, and performance metrics.
- **`strategy/`** — `Strategy` base + built-ins (`MACross`, `VolatilityBreakout`).
- **`rl/`** — `ChartFollowingEnv` (Gymnasium) for RL experiments.
- **`state/`** + **`ops/`** + **`web/`** — the cockpit (shared state, toolbelt, dashboard).

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
pytest -q          # 49 tests
python examples/backtest_synthetic.py
```
