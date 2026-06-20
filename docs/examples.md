# Worked examples

Real `yq` sessions on seeded data (BTCUSDT / ETHUSDT / SOLUSDT, 500×1d each) —
every command below was actually run; the JSON is its real output. Pipe output is
JSON; in a terminal the same data renders as colored tables/boxes.

!!! note "Setup"
    These use a local store so they run offline. In normal use `yq collect`
    fills the store from an exchange first. All commands accept `--store` /
    `--state` to point at specific files.

## Research a strategy

```console
$ yq backtest BTCUSDT 1d keltner_breakout
{
  "bars": 479, "start_equity": 10000.0, "end_equity": 10379.65,
  "total_return": 0.038, "sharpe": 1.732, "sortino": 1.908, "calmar": 4.22,
  "max_drawdown": -0.0068, "num_trades": 24, "num_closed": 5, "win_rate": 0.0
}
```

!!! tip "Reading it"
    `total_return` is equity-based (includes the **unrealized** mark-to-market of
    an open position), while `win_rate` / `best_trade` cover only **closed**
    round-trips. A trend strategy that ends holding a winning long can show a
    positive return with few/no closed wins — the gains are still on the book.

## Optimize parameters

```console
$ yq optimize BTCUSDT 1d macross --metric sharpe
{
  "metric": "sharpe",
  "best_params": {"fast": 20, "slow": 100},
  "best_score": 1.431,
  "top": [
    {"params": {"fast": 20, "slow": 100}, "score": 1.431},
    {"params": {"fast": 10, "slow": 100}, "score": 1.092},
    {"params": {"fast": 5,  "slow": 100}, "score": 1.015}
  ]
}
```

### Validate out-of-sample (walk-forward)

```console
$ yq optimize BTCUSDT 1d macross --walk-forward 4
{
  "metric": "sharpe", "n_folds": 4, "avg_out_of_sample": 0.348,
  "folds": [
    {"fold": 0, "best_params": {"fast": 10, "slow": 50}, "in_sample": 0.0,   "oos_sharpe": -1.365},
    {"fold": 1, "best_params": {"fast": 20, "slow": 30}, "in_sample": 0.307, "oos_sharpe": 0.0},
    {"fold": 2, "best_params": {"fast": 5,  "slow": 50}, "in_sample": 0.0,   "oos_sharpe": 2.757},
    {"fold": 3, "best_params": {"fast": 5,  "slow": 50}, "in_sample": 2.757, "oos_sharpe": 0.0}
  ]
}
```

The per-fold gap between `in_sample` and `oos_sharpe` is the overfitting tell —
chase the `avg_out_of_sample`, not the grid's best in-sample score. The dashboard
Research panel plots exactly this, in-sample vs out-of-sample per fold:

![Walk-forward in-sample vs out-of-sample per fold](assets/walkforward.png)

## Blend strategies (ensemble)

```console
$ yq ensemble BTCUSDT 1d --members macross,supertrend,rsi_reversion --rule weighted --threshold 0.4
{
  "bars": 449, "total_return": 0.0013, "sharpe": 0.533, "num_trades": 3,
  "members": ["macross", "supertrend", "rsi_reversion"], "rule": "weighted"
}
```

## Portfolio backtest

```console
$ yq portfolio BTCUSDT ETHUSDT SOLUSDT --strategy keltner_breakout
{
  "portfolio": {"total_return": 0.1808, "sharpe": 2.254, "max_drawdown": -0.0333},
  "per_symbol": {
    "BTCUSDT": {"total_return": 0.1139, "weight": 0.3333},
    "ETHUSDT": {"total_return": -0.0558, "weight": 0.3333},
    "SOLUSDT": {"total_return": 0.4843, "weight": 0.3333}
  }
}
```

## Risk-parity target weights

Size holdings by inverse volatility so each contributes roughly equal risk:

```console
$ yq target --risk-parity BTCUSDT ETHUSDT SOLUSDT
{"BTCUSDT": 0.3667, "ETHUSDT": 0.3131, "SOLUSDT": 0.3202}

$ yq rebalance --execute     # then move holdings toward those weights
```

## Trade (paper) and report

```console
$ yq trade BTCUSDT BUY 0.1 --price 65000 --mode paper
{"id": 1, "status": "filled", "mode": "paper", "side": "BUY", "quantity": 0.1, "price": 65000.0}

$ yq trade BTCUSDT SELL 0.1 --price 71000 --mode paper
{"id": 2, "status": "filled", "side": "SELL", "price": 71000.0}

$ yq report
{"equity_now": 10586.4, "realized_pnl": 592.9, "total_return": 0.0593,
 "closed_trades": 1, "win_rate": 1.0}
```

## Memory: journal then recall

```console
$ yq journal "entered BTC on keltner breakout, vol expanding" --tag thesis --importance 8
$ yq journal "minor note" --importance 2
$ yq recall "BTC breakout"
memories: [(8.0, "entered BTC on keltner breakout, vol e…")]   # low-importance note filtered out
open_positions: []
```

## Self-improvement: author a strategy

```console
$ yq new strategy demo_breakout
{"created": "user_plugins/strategies/demo_breakout.py", "kind": "strategy"}

$ yq plugins
{"strategies": ["demo_breakout"], "indicators": [], "errors": []}

$ yq backtest BTCUSDT 1d demo_breakout      # usable immediately
```

## Inspect the latest features

```console
$ yq features BTCUSDT 1d
{"close": 115.33, "rsi_14": 59.1, "adx_14": 40.75, "atr_pct": 0.0285, "macd_hist": -0.716}
```

---

Every command above is also a dashboard action — see [The dashboard](dashboard.md)
for the point-and-click equivalents (Research, Manual trade, Control center, …).
