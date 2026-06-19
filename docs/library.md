# Python library

The CLI is a thin layer over a clean, tested framework you can use directly — in a
notebook, a script, or a Claude Code session.

```python
from yammyquant import Candle, Backtest, MACross
result = Backtest(candle, MACross(5, 20), cash=10_000, fee=0.001).run()
print(result)   # Sharpe, max drawdown, win rate, profit factor, ...
```

## Package map

```
src/yammyquant/
├── data/        # Candle, indicators, DuckDB store, sources, feature pipeline
├── backtest/    # order, portfolio, broker, engine, risk, optimize, metrics
├── strategy/    # Strategy base + MACross / VolatilityBreakout / RSIReversion / Donchian
├── feeds/       # information layer: RSS news, DART disclosures, sentiment
├── exchanges/   # native KR + crypto adapters + ccxt, one config surface
├── rl/          # gymnasium env (ChartFollowingEnv)
├── state/       # LiveState — shared SQLite cockpit state
├── ops/         # operator toolbelt: trading, operator fns, `yq` CLI
└── web/         # FastAPI cockpit + static SPA (Plotly, no build step)
```

## What each module gives you

- **`data/`** — typed `Candle` + dependency-free indicators (sma/ema/rsi/atr/
  bbands/macd), a DuckDB+Parquet store, a Binance source + `CCXTSource`, and a
  feature pipeline (`features.py`: returns, realized vol, volume z-score, RSI,
  trend, ATR%).
- **`backtest/`** — order/portfolio/broker/engine with fees & slippage; a risk
  layer (`RiskConfig`); optimization (`grid_search`, `walk_forward`); and metrics
  (Sharpe, Sortino, Calmar, max drawdown, CAGR, volatility, win rate, profit
  factor, trade stats).
- **`strategy/`** — `Strategy` base + built-ins; cockpit-toggleable.
- **`feeds/`** — `RSSFeed`, `DartFeed`, keyword `score_text`, `NewsItem`.
- **`exchanges/`** — `get_exchange(name)` returns a native adapter (data + balances
  + orders) for Binance/Upbit/Bithumb/Coinone/Korbit/KIS/Toss, or any ccxt venue.
- **`state/`** — `LiveState`, the shared SQLite store behind the CLI and dashboard.
- **`ops/`** — the operator functions (`collect`, `backtest`, `brief`, `decide`,
  `recall`, …) exposed through the `yq` CLI.

!!! note "Extending it"
    When you write new strategies / collectors / trainers, expose them through
    `ops/` so they show up in both the cockpit and the CLI.
```python
result = Backtest(candle, strat).run()
result.stats        # dict of headline metrics
result.equity       # equity curve
result.trades       # per-trade records
```
