"""``yq`` — the operator command line.

The toolbelt Claude Code (or you) invoke to run the platform. Every command
operates on a shared SQLite state file (``--state``) and, where relevant, a
DuckDB candle store (``--store``), so the dashboard stays in sync.

    yq inbox                       # read instructions left in the dashboard
    yq collect BTCUSDT 1d 1h       # backfill candles
    yq backtest BTCUSDT 1d macross --fast 5 --slow 20
    yq scan BTCUSDT ETHUSDT --interval 1d --strategy macross
    yq trade BTCUSDT BUY 0.1 --price 65000 --mode paper
    yq approve 7
    yq dashboard                   # launch the cockpit web app
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Optional

from yammyquant.state.store import LiveState
from yammyquant.data.sources.store import DuckDBStore
from yammyquant.ops import operator as ops
from yammyquant.ops.trading import TradeManager


def _print(obj) -> None:
    print(json.dumps(obj, indent=2, default=str))


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="yq", description="YammyQuant operator CLI")
    parser.add_argument("--state", default="yammyquant_state.db", help="SQLite state file")
    parser.add_argument("--store", default="data_store", help="DuckDB candle store dir")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("inbox", help="read/clear instructions left in the dashboard")
    p.add_argument("--all", action="store_true", help="show read messages too")
    p.add_argument("--mark-read", action="store_true", help="mark unread messages as read")

    p = sub.add_parser("collect", help="backfill candles from Binance")
    p.add_argument("ticker")
    p.add_argument("intervals", nargs="+")

    p = sub.add_parser("backtest", help="run a backtest")
    p.add_argument("ticker")
    p.add_argument("interval")
    p.add_argument("strategy")
    p.add_argument("--fast", type=int)
    p.add_argument("--slow", type=int)
    p.add_argument("--k", type=float)
    p.add_argument("--size", type=float)
    p.add_argument("--cash", type=float, default=10_000.0)
    p.add_argument("--fee", type=float, default=0.001)
    p.add_argument("--start")
    p.add_argument("--end")

    p = sub.add_parser("scan", help="scan tickers for signals")
    p.add_argument("tickers", nargs="+")
    p.add_argument("--interval", default="1d")
    p.add_argument("--strategy", default="macross")

    p = sub.add_parser("features", help="compute & store candle-derived features")
    p.add_argument("ticker")
    p.add_argument("interval")

    p = sub.add_parser("strategies", help="list or toggle strategies")
    p.add_argument("--enable")
    p.add_argument("--disable")

    p = sub.add_parser("train", help="train an RL agent on stored candles")
    p.add_argument("ticker")
    p.add_argument("interval")
    p.add_argument("--timesteps", type=int, default=10_000)
    p.add_argument("--algo", default="SAC", choices=["SAC", "PPO"])
    p.add_argument("--window", type=int, default=10)
    p.add_argument("--no-deadend", action="store_true")

    p = sub.add_parser("trade", help="submit a trade (paper fills now; live queues)")
    p.add_argument("ticker")
    p.add_argument("side", choices=["BUY", "SELL", "buy", "sell"])
    p.add_argument("quantity", type=float)
    p.add_argument("--price", type=float, required=True)
    p.add_argument("--mode", choices=["paper", "live"], default="paper")
    p.add_argument("--rationale", default="")

    p = sub.add_parser("approve", help="approve a pending trade")
    p.add_argument("trade_id", type=int)
    p = sub.add_parser("reject", help="reject a pending trade")
    p.add_argument("trade_id", type=int)

    sub.add_parser("status", help="print the full cockpit state snapshot")

    p = sub.add_parser("dashboard", help="launch the cockpit web app")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8000)

    args = parser.parse_args(argv)
    state = LiveState(args.state)

    if args.cmd == "inbox":
        msgs = state.inbox(only_unread=not args.all)
        _print(msgs)
        if args.mark_read:
            state.mark_inbox_read([m["id"] for m in msgs if m["status"] == "unread"])
        return 0

    if args.cmd == "collect":
        _print(ops.collect(DuckDBStore(args.store), args.ticker, args.intervals, state))
        return 0

    if args.cmd == "backtest":
        params = {k: v for k, v in
                  {"fast": args.fast, "slow": args.slow, "k": args.k, "size": args.size}.items()
                  if v is not None}
        _print(ops.backtest(DuckDBStore(args.store), args.ticker, args.interval,
                            args.strategy, params, args.cash, args.fee,
                            args.start, args.end, state))
        return 0

    if args.cmd == "scan":
        _print(ops.scan(DuckDBStore(args.store), args.tickers, args.interval,
                        args.strategy, state=state))
        return 0

    if args.cmd == "features":
        _print(ops.features(DuckDBStore(args.store), args.ticker, args.interval, state=state))
        return 0

    if args.cmd == "strategies":
        if args.enable:
            state.set(f"strategy.{args.enable}.enabled", True)
        if args.disable:
            state.set(f"strategy.{args.disable}.enabled", False)
        _print({"available": sorted(ops.STRATEGIES),
                "enabled": ops.enabled_strategies(state)})
        return 0

    if args.cmd == "train":
        from yammyquant.ops import training
        _print(training.train(DuckDBStore(args.store), args.ticker, args.interval,
                              timesteps=args.timesteps, window=args.window,
                              algo=args.algo, deadend=not args.no_deadend, state=state))
        return 0

    if args.cmd == "trade":
        tm = TradeManager(state)
        _print(tm.submit(args.ticker, args.side, args.quantity, args.price,
                         args.mode, args.rationale))
        return 0

    if args.cmd == "approve":
        _print(TradeManager(state).approve(args.trade_id))
        return 0

    if args.cmd == "reject":
        _print(TradeManager(state).reject(args.trade_id))
        return 0

    if args.cmd == "status":
        _print(state.snapshot())
        return 0

    if args.cmd == "dashboard":
        from yammyquant.web.app import serve
        serve(host=args.host, port=args.port, state_path=args.state, store_path=args.store)
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(main())
