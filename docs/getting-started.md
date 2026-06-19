# Getting started

## Install

=== "Everything"

    ```bash
    pip install -e '.[all]'
    ```

=== "Just the dashboard"

    ```bash
    pip install -e '.[web]'
    ```

=== "Binance only"

    ```bash
    pip install -e '.[binance]'
    ```

=== "News / feeds"

    ```bash
    pip install -e '.[feeds]'
    ```

For development (tests, linters):

```bash
pip install -e '.[all,dev]'
pytest -q          # 147 tests
```

## Quickstart

```bash
# 1. collect candles (needs network; or seed your own — see examples/)
yq collect BTCUSDT 1d 1h

# 2. research
yq features BTCUSDT 1d
yq backtest BTCUSDT 1d macross --fast 5 --slow 20
yq optimize BTCUSDT 1d macross --walk-forward 4
yq brief BTCUSDT                              # one-screen research digest

# 3. operate the account
yq watch add BTCUSDT --interval 1d
yq risk set max_open_positions=5 daily_loss_limit=200
yq decide --weight 0.1 --execute             # signals → risk-sized paper orders
yq cycle                                     # refresh → scan → mark → notify

# 4. launch the cockpit
yq dashboard          # → http://127.0.0.1:8000
```

## The cockpit

`yq dashboard` serves a dependency-free SPA (Plotly via CDN, no node build step).
In it you can watch price/equity charts, approve or reject pending trades, close
positions, toggle strategies, and **leave instructions** for the operator — which
Claude Code reads with `yq recall` / `yq inbox` on its next run.

!!! info "State lives on disk"
    Both the CLI and the dashboard share `yammyquant_state.db` (SQLite) and
    `data_store/` (DuckDB/Parquet). Anything the operator does is durable and
    visible live in the dashboard.

## Money safety, up front

Paper trading is the default. **Live orders require two gates** — the env flag
`YQ_ALLOW_LIVE=1` *and* explicit human approval. See [Money safety](safety.md).
