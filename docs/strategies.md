# Strategies & risk

## Built-in strategies

| Name | Idea |
|---|---|
| `macross` | Moving-average crossover trend following. |
| `volatility_breakout` | Intraday range breakout (k-factor). |
| `rsi_reversion` | Mean reversion on RSI extremes. |
| `donchian_breakout` | Channel breakout over a lookback. |

Toggle them from the cockpit (or `yq strategies --disable rsi_reversion`); the
enabled set is read via `enabled_strategies(state)` and drives `yq decide`.

## Backtesting

```python
from yammyquant import Candle, Backtest, MACross
result = Backtest(candle, MACross(5, 20), cash=10_000, fee=0.001).run()
print(result)   # Sharpe, Sortino, Calmar, max drawdown, CAGR, win rate, ...
```

## Risk layer (backtests)

```python
from yammyquant.backtest.engine import Backtest
from yammyquant.backtest.risk import RiskConfig

Backtest(candle, strategy, risk=RiskConfig(
    sizing="volatility",   # volatility-targeted position sizing
    stop_loss=0.05,
    take_profit=0.10,
    max_drawdown=0.20,     # drawdown kill-switch
))
```

## Account risk policy (live & paper)

The account-level risk policy is enforced on **every** order — it can reject a
trade before it fills:

```bash
yq risk set max_open_positions=5 max_order_value=1000 daily_loss_limit=200
```

| Field | Meaning |
|---|---|
| `max_order_value` | Cap on a single order's notional. |
| `max_position_value` | Cap on a single position's notional. |
| `max_open_positions` | Cap on simultaneous positions. |
| `max_symbol_weight` | Cap on one symbol's share of equity. |
| `daily_loss_limit` | Halt new entries after this realized loss in a day. |
| `cooldown_minutes` | Minimum gap between trades on a symbol. |

## Signal → order: `yq decide`

`yq decide` aggregates enabled-strategy signals per watchlist symbol into concrete,
risk-sized orders (entry sized to a fraction of equity; exits flatten). Dry-run by
default; `--execute` submits; `--type limit` rests live orders until `yq sync`
settles them. Set `auto_trade=true` to let `yq cycle` / the scheduler call
`decide --execute` automatically (paper unless `trade_mode=live`).

## Strategy decay

```bash
yq expect BTCUSDT 1d macross      # record a backtest baseline
yq decay                          # warn when realized < baseline (edge erosion)
```
