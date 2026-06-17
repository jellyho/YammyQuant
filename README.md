# YammyQuant

A small, modern quant framework for crypto **backtesting**, **live trading**,
and **reinforcement-learning** experiments.

> **0.2 rewrite.** This is a ground-up re-architecture of the original project.
> The old code is preserved under [`legacy/`](legacy/) for reference. See
> [`legacy/README.md`](legacy/README.md) for the old→new mapping and an
> important security notice about secrets in git history.

## Highlights

- **Typed `Candle`** OHLCV container with dependency-free vectorized indicators
  (`sma`, `ema`, `rsi`, `atr`, `bbands`, `macd`) — no more `finta`.
- **DuckDB + Parquet** local data store — zero-config, no MySQL server, fast
  range reads, parameterized queries (no SQL injection).
- **Clean backtest engine**: `Strategy` → `Broker` → `Portfolio` with fees,
  slippage, an equity curve, and performance metrics (Sharpe, MDD, win rate,
  profit factor, CAGR).
- **Gymnasium RL env** (`ChartFollowingEnv`) compatible with current
  Stable-Baselines3.
- **Secrets via environment variables**, never hardcoded. Tests included.

## Install

```bash
pip install -e .              # core (backtesting)
pip install -e '.[binance]'   # + Binance data source
pip install -e '.[rl]'        # + gymnasium / stable-baselines3
pip install -e '.[all,dev]'   # everything + test tooling
```

## Quickstart

```python
import pandas as pd
from yammyquant import Candle, Backtest, MACross

candle = Candle("BTCUSDT", df, interval="1d")          # df has open/high/low/close/volume
result = Backtest(candle, MACross(fast=5, slow=20, size=0.1),
                  cash=10_000, fee=0.001).run()
print(result)            # headline stats
print(result.trades)     # trade log (DataFrame)
print(result.equity_curve)
```

Runnable, no-network demo:

```bash
python examples/backtest_synthetic.py
```

## Downloading & storing data

```python
from yammyquant.data.sources.store import DuckDBStore
from yammyquant.data.sources.binance import backfill

store = DuckDBStore("data_store")
backfill(store, "BTCUSDT", ["1d", "1h"])               # resumes from last stored bar
candle = store.read("BTCUSDT", "1d", start="2023-01-01 00:00:00")
```

Set Binance keys (optional for public data) via env vars:
`BINANCE_API_KEY`, `BINANCE_SECRET_KEY`.

## Writing a strategy

```python
from yammyquant import Strategy, Order, Action

class BuyTheDip(Strategy):
    warmup = 20

    def on_bar(self, window):
        rsi = window.ind.rsi(14).iloc[-1]
        if rsi < 30:
            return [Order(Action.BUY, window.ticker, quantity=0.1)]
        if rsi > 70:
            return [Order(Action.SELL, window.ticker, quantity=0.1)]
        return []
```

The engine calls `on_bar` once per bar with a `Candle` window whose **last** row
is the current bar.

## Reinforcement learning

```bash
pip install -e '.[rl]'
python examples/train_rl.py
```

`ChartFollowingEnv` unifies the three legacy gym environments into one
configurable, Gymnasium-compliant env (`reset` → `(obs, info)`, `step` →
5-tuple).

## Project layout

```
src/yammyquant/
├── data/            # Candle, indicators, data sources (DuckDB, Binance)
├── backtest/        # order, portfolio, broker, engine
├── strategy/        # Strategy base + built-ins (MACross, VolatilityBreakout)
├── metrics/         # performance statistics
├── rl/              # gymnasium environment
└── notify/          # Discord webhook notifier
tests/               # pytest suite
examples/            # runnable examples
legacy/              # original pre-0.2 code (reference only)
```

## Development

```bash
pip install -e '.[all,dev]'
pytest -q
```
