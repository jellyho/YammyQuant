# Strategies & risk

## Built-in strategies

A broad library across every classic family. Toggle them from the cockpit (or
`yq strategies --disable rsi_reversion`); the enabled set is read via
`enabled_strategies(state)` and drives `yq decide`. Every strategy is optimizable
via `yq optimize <sym> <interval> <name>` (each ships a default parameter grid).

=== "Trend following"

    | Name | Idea |
    |---|---|
    | `macross` | SMA fast/slow crossover. |
    | `ema_cross` | EMA fast/slow crossover (scalper's trigger). |
    | `triple_ema` | EMA ribbon (fast/mid/slow) alignment. |
    | `macd_momentum` | MACD line / signal crossover. |
    | `supertrend` | ATR trailing trend; trade direction flips. |
    | `adx_trend` | +DI/−DI crossover gated by ADX strength. |
    | `parabolic_sar` | Parabolic SAR flips vs price. |

=== "Breakout / volatility"

    | Name | Idea |
    |---|---|
    | `volatility_breakout` | Larry Williams k-factor range breakout. |
    | `donchian_breakout` | Break of the N-bar high/low channel. |
    | `bollinger_breakout` | Close breaking outside the Bollinger Bands. |
    | `keltner_breakout` | Break of the Keltner channel (EMA ± ATR). |

=== "Mean reversion / scalping"

    | Name | Idea |
    |---|---|
    | `rsi_reversion` | Buy oversold / sell overbought RSI crossings. |
    | `bollinger_reversion` | Fade band touches back toward the mean. |
    | `stochastic_scalp` | %K/%D crossover out of OS/OB zones. |
    | `stoch_rsi_scalp` | Stochastic-RSI %K/%D crossover. |
    | `williams_r_scalp` | Williams %R reversal out of extremes. |
    | `cci_reversion` | CCI reversal at ±threshold. |
    | `mfi_reversion` | Money-Flow-Index (volume RSI) reversal. |
    | `vwap_reversion` | Fade deviations from rolling VWAP. |

## Indicators

All strategies build on a dependency-free indicator library, callable directly:
`candle.ind.<name>(...)`. 30+ indicators are registered:

| Family | Indicators |
|---|---|
| Moving averages | `sma` `ema` `wma` `hma` `dema` `tema` `vwma` `vwap` |
| Momentum / oscillators | `rsi` `macd` `ppo` `roc` `momentum` `trix` `stoch` `stoch_rsi` `williams_r` `cci` `mfi` |
| Volatility / channels | `atr` `tr` `natr` `stddev` `zscore` `bbands` `bbwidth` `keltner` `donchian` `supertrend` `psar` `adx` |
| Volume | `obv` `cmf` `vwma` `mfi` |

```python
candle.ind.rsi(14)              # Series
candle.ind.macd(12, 26, 9)      # DataFrame: macd / signal / hist
candle.ind.supertrend(10, 3)    # DataFrame: supertrend / direction
```

Multi-output indicators (`macd`, `stoch`, `stoch_rsi`, `bbands`, `adx`,
`keltner`, `donchian`, `supertrend`) return a `DataFrame`; the rest return a
`Series` aligned to the candle index.

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
