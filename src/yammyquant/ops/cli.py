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

    p = sub.add_parser("collect", help="backfill candles from an exchange")
    p.add_argument("ticker")
    p.add_argument("intervals", nargs="+")
    p.add_argument("--exchange", default="binance",
                   help="binance (resumable) | upbit | bithumb | kis | any ccxt id")
    p.add_argument("--count", type=int, default=200, help="bars to fetch (non-binance)")

    sub.add_parser("exchanges", help="list supported exchanges")

    p = sub.add_parser("config", help="view/set central exchange config (keys, base urls, default)")
    p.add_argument("action", choices=["show", "set", "default", "path"])
    p.add_argument("args", nargs="*",
                   help="set: <exchange> field=value ...   |   default: <exchange>")

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

    p = sub.add_parser("optimize", help="grid-search strategy params (optionally walk-forward)")
    p.add_argument("ticker")
    p.add_argument("interval")
    p.add_argument("strategy")
    p.add_argument("--metric", default="sharpe")
    p.add_argument("--walk-forward", type=int, default=0, metavar="N",
                   help="number of walk-forward splits (0 = in-sample grid search)")

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

    p = sub.add_parser("mark", help="mark open positions to market (live prices)")
    p.add_argument("--exchange")
    p.add_argument("--interval", default="1m")

    sub.add_parser("doctor", help="health check: data freshness, config, account")
    sub.add_parser("report", help="performance report (realized PnL, drawdown, ...)")

    p = sub.add_parser("reconcile", help="compare local positions to exchange balances")
    p.add_argument("--exchange")

    p = sub.add_parser("risk", help="view/set the account risk policy")
    p.add_argument("action", choices=["show", "set"])
    p.add_argument("args", nargs="*", help="set: field=value ...")

    p = sub.add_parser("journal", help="operator journal: add a note, or list")
    p.add_argument("text", nargs="?", help="note text (omit to list)")
    p.add_argument("--tag", default="")
    p.add_argument("--limit", type=int, default=50)

    p = sub.add_parser("watch", help="manage the watchlist")
    p.add_argument("action", choices=["add", "rm", "list"])
    p.add_argument("symbol", nargs="?")
    p.add_argument("--exchange", default="")
    p.add_argument("--interval", default="1d")
    p.add_argument("--note", default="")

    p = sub.add_parser("decide", help="turn signals into risk-sized orders (dry-run unless --execute)")
    p.add_argument("--exchange")
    p.add_argument("--mode", choices=["paper", "live"], default="paper")
    p.add_argument("--weight", type=float, help="target fraction of equity per entry")
    p.add_argument("--type", dest="order_type", choices=["market", "limit"], default="market")
    p.add_argument("--execute", action="store_true", help="actually submit the orders")

    p = sub.add_parser("rebalance", help="move portfolio toward target weights")
    p.add_argument("--exchange")
    p.add_argument("--mode", choices=["paper", "live"], default="paper")
    p.add_argument("--band", type=float, default=0.02, help="tolerance band around target")
    p.add_argument("--execute", action="store_true")

    p = sub.add_parser("target", help="view/set portfolio target weights")
    p.add_argument("assignments", nargs="*", help="SYMBOL=weight ... (empty = show)")

    p = sub.add_parser("expect", help="record a backtest baseline for decay tracking")
    p.add_argument("ticker")
    p.add_argument("interval")
    p.add_argument("strategy")

    sub.add_parser("decay", help="compare realized performance to recorded baselines")

    p = sub.add_parser("sync", help="poll & settle submitted live orders")
    p.add_argument("--exchange")

    p = sub.add_parser("cycle", help="run one maintenance cycle (refresh/scan/mark/notify)")
    p.add_argument("--exchange")

    p = sub.add_parser("schedule", help="run maintenance cycles on an interval")
    p.add_argument("--interval", type=int, default=300, help="seconds between cycles")
    p.add_argument("--exchange")
    p.add_argument("--max-cycles", type=int)

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
        _print(ops.collect(DuckDBStore(args.store), args.ticker, args.intervals, state,
                           exchange=args.exchange, count=args.count))
        return 0

    if args.cmd == "exchanges":
        from yammyquant.exchanges import list_exchanges
        _print(list_exchanges())
        return 0

    if args.cmd == "config":
        from yammyquant.exchanges import config as xcfg

        def _coerce(v: str):
            low = v.lower()
            if low in ("true", "false"):
                return low == "true"
            return v

        if args.action == "show":
            _print(xcfg.describe())
        elif args.action == "path":
            _print({"config_file": str(xcfg.config_path(for_write=True))})
        elif args.action == "default":
            if not args.args:
                print("usage: yq config default <exchange>"); return 1
            cfg = xcfg.load_config(); cfg["default_exchange"] = args.args[0].lower()
            path = xcfg.save_config(cfg)
            _print({"default_exchange": args.args[0].lower(), "saved": str(path)})
        elif args.action == "set":
            if len(args.args) < 2 or any("=" not in a for a in args.args[1:]):
                print("usage: yq config set <exchange> field=value [field=value ...]"); return 1
            exchange = args.args[0].lower()
            for assignment in args.args[1:]:
                field_name, value = assignment.split("=", 1)
                path = xcfg.set_value(exchange, field_name, _coerce(value))
            _print({"exchange": exchange, "saved": str(path),
                    "status": xcfg.describe()["exchanges"].get(exchange)})
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

    if args.cmd == "optimize":
        _print(ops.optimize(DuckDBStore(args.store), args.ticker, args.interval,
                           args.strategy, metric=args.metric,
                           walk_forward_splits=args.walk_forward, state=state))
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

    if args.cmd == "mark":
        _print(ops.mark(state, exchange=args.exchange, interval=args.interval))
        return 0

    if args.cmd == "doctor":
        _print(ops.doctor(DuckDBStore(args.store), state))
        return 0

    if args.cmd == "report":
        _print(ops.report(state))
        return 0

    if args.cmd == "reconcile":
        _print(ops.reconcile(state, exchange=args.exchange))
        return 0

    if args.cmd == "risk":
        from yammyquant.ops.risk_policy import AccountRiskPolicy
        if args.action == "set":
            policy = AccountRiskPolicy.load(state)
            for assignment in args.args:
                if "=" not in assignment:
                    print("usage: yq risk set field=value ..."); return 1
                field_name, value = assignment.split("=", 1)
                setattr(policy, field_name,
                        None if value.lower() in ("", "none") else float(value))
            policy.save(state)
        from dataclasses import asdict
        _print(asdict(AccountRiskPolicy.load(state)))
        return 0

    if args.cmd == "journal":
        if args.text:
            jid = state.add_journal(args.text, tag=args.tag)
            _print({"id": jid, "tag": args.tag, "text": args.text})
        else:
            _print(state.journal(limit=args.limit))
        return 0

    if args.cmd == "watch":
        if args.action == "add":
            if not args.symbol:
                print("usage: yq watch add SYMBOL [--exchange --interval --note]"); return 1
            state.add_watch(args.symbol, args.exchange, args.interval, args.note)
        elif args.action == "rm":
            if not args.symbol:
                print("usage: yq watch rm SYMBOL"); return 1
            state.remove_watch(args.symbol)
        _print(state.watchlist())
        return 0

    if args.cmd == "decide":
        _print(ops.decide(DuckDBStore(args.store), state, exchange=args.exchange,
                         mode=args.mode, weight=args.weight, execute=args.execute,
                         order_type=args.order_type))
        return 0

    if args.cmd == "rebalance":
        _print(ops.rebalance(DuckDBStore(args.store), state, exchange=args.exchange,
                            mode=args.mode, band=args.band, execute=args.execute))
        return 0

    if args.cmd == "target":
        if args.assignments:
            targets = state.get("targets", {})
            for kv in args.assignments:
                if "=" not in kv:
                    print("usage: yq target SYMBOL=weight ..."); return 1
                sym, w = kv.split("=", 1)
                targets[sym] = float(w)
            state.set("targets", targets)
        _print(state.get("targets", {}))
        return 0

    if args.cmd == "expect":
        _print(ops.record_expectation(DuckDBStore(args.store), state,
                                     args.ticker, args.interval, args.strategy))
        return 0

    if args.cmd == "decay":
        _print(ops.decay_check(state))
        return 0

    if args.cmd == "sync":
        _print(ops.sync_orders(state, exchange=args.exchange))
        return 0

    if args.cmd == "cycle":
        _print(ops.run_cycle(DuckDBStore(args.store), state, exchange=args.exchange))
        return 0

    if args.cmd == "schedule":
        from yammyquant.ops.scheduler import run_loop
        run_loop(args.state, args.store, interval_seconds=args.interval,
                 exchange=args.exchange, max_cycles=args.max_cycles)
        return 0

    if args.cmd == "dashboard":
        from yammyquant.web.app import serve
        serve(host=args.host, port=args.port, state_path=args.state, store_path=args.store)
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(main())
