"""End-to-end example: download from Binance -> store locally -> backtest.

Requires the optional binance extra and network access:
    pip install 'yammyquant[binance]'
    python examples/backfill_and_backtest.py
"""

from yammyquant import Backtest, MACross
from yammyquant.data.sources.store import DuckDBStore
from yammyquant.data.sources.binance import backfill


def main():
    store = DuckDBStore("data_store")

    # 1) backfill BTCUSDT daily candles (resumes from last stored bar)
    backfill(store, "BTCUSDT", ["1d"])

    # 2) read a date range back out as a Candle
    candle = store.read("BTCUSDT", "1d", start="2023-01-01 00:00:00")

    # 3) backtest a strategy over it
    result = Backtest(candle, MACross(5, 20, size=0.1), cash=10_000, fee=0.001).run()
    print(result)


if __name__ == "__main__":
    main()
