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
import os
import re
import sys
import unicodedata
from typing import Optional

from yammyquant.state.store import LiveState
from yammyquant.data.sources.store import DuckDBStore
from yammyquant.ops import operator as ops
from yammyquant.ops.trading import TradeManager

# ---- cute output -----------------------------------------------------------
# Pretty (colored, boxed, sparklines, CJK-aware) when writing to a terminal;
# clean JSON when piped or with --json, so machine consumers parse as before.
_COLOR = sys.stdout.isatty() and os.getenv("NO_COLOR") is None and os.getenv("TERM") != "dumb"
_FORCE_JSON = False
_TITLE = ""          # set per command in main(), used as the panel header

BANNER = r"""
  __ _  __ _ _ __ ___  _ __ ___  _   _
 / _` |/ _` | '_ ` _ \| '_ ` _ \| | | |   {accent}YammyQuant{r} · agentic quant cockpit
| (_| | (_| | | | | | | | | | | | |_| |   {dim}paper-by-default · you are the operator{r}
 \__, |\__,_|_| |_| |_|_| |_| |_|\__, |   {dim}yq <command> --help · yq dashboard{r}
 |___/                           |___/
"""

_ANSI = re.compile(r"\033\[[0-9;]*m")
# Unicode box/sparkline look best, but their glyphs are East-Asian "Ambiguous":
# some CJK terminals render them two columns wide, breaking alignment. Set
# YQ_ASCII=1 for a pure-ASCII layout (every structural glyph is exactly 1 cell).
_ASCII = os.getenv("YQ_ASCII", "") not in ("", "0", "false", "no")
_SPARK = " .:-=+*#" if _ASCII else "▁▂▃▄▅▆▇█"
_BOX = (dict(tl="+", tr="+", bl="+", br="+", h="-", v="|") if _ASCII
        else dict(tl="╭", tr="╮", bl="╰", br="╯", h="─", v="│"))


# Truecolor palette — matches the web cockpit (#4da3ff / #3fb950 / #f85149 / …).
def _rgb(r: int, g: int, b: int) -> str:
    return f"\033[38;2;{r};{g};{b}m"


class _Hue:
    R = "\033[0m"
    B = "\033[1m"
    DIM = "\033[2m"
    ACCENT = _rgb(77, 163, 255)    # #4da3ff
    GREEN = _rgb(63, 185, 80)      # #3fb950
    RED = _rgb(248, 81, 73)        # #f85149
    AMBER = _rgb(210, 153, 34)     # #d29922
    PURPLE = _rgb(163, 113, 247)   # #a371f7
    LABEL = _rgb(121, 192, 255)    # #79c0ff  (soft blue for keys)
    GREY = _rgb(110, 118, 129)     # #6e7681
    # backwards-compatible aliases
    CYAN = ACCENT
    YEL = AMBER
    BLUE = ACCENT
    MAG = PURPLE


def _c(text, color: str) -> str:
    return f"{color}{text}{_Hue.R}" if _COLOR else str(text)


def _dwidth(s: str) -> int:
    """Visible width: strip ANSI, count East-Asian wide/full-width glyphs as 2."""
    s = _ANSI.sub("", s)
    return sum(2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1 for ch in s)


def _pad(s: str, width: int) -> str:
    return s + " " * max(0, width - _dwidth(s))


def banner() -> str:
    return BANNER.format(
        accent=_Hue.CYAN + _Hue.B if _COLOR else "",
        dim=_Hue.DIM if _COLOR else "",
        r=_Hue.R if _COLOR else "",
    )


def _sparkline(values) -> str:
    nums = [float(x) for x in values if isinstance(x, (int, float))]
    if len(nums) < 2:
        return ""
    lo, hi = min(nums), max(nums)
    rng = (hi - lo) or 1.0
    n = len(_SPARK) - 1
    bars = "".join(_SPARK[min(n, int((v - lo) / rng * n))] for v in nums[-40:])
    trend = _Hue.GREEN if nums[-1] >= nums[0] else _Hue.RED
    return _c(bars, trend)


def _plain(value) -> str:
    if value is None:
        return "-"
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, float):
        if value != value:                       # NaN
            return "-"
        a = abs(value)
        if a != 0 and (a >= 1e7 or a < 1e-4):
            return f"{value:.4g}"
        return (f"{value:,.4f}".rstrip("0").rstrip(".")) or "0"
    if isinstance(value, int) and abs(value) >= 1000:
        return f"{value:,}"
    return str(value)


def _color_for(key, value) -> Optional[str]:
    """Pick an ANSI color for a value based on its key/content (or None)."""
    if value is None:
        return _Hue.GREY
    if isinstance(value, bool):
        return _Hue.GREEN if value else _Hue.GREY
    s, low = str(value), str(key).lower()
    if s in ("BUY", "buy", "long"):
        return _Hue.GREEN
    if s in ("SELL", "sell", "short"):
        return _Hue.RED
    if s in ("filled", "approved", "ok", "healthy", "enabled"):
        return _Hue.GREEN
    if s in ("pending", "submitted", "partial", "queued"):
        return _Hue.YEL
    if s in ("rejected", "error", "failed", "stale", "disabled"):
        return _Hue.RED
    if isinstance(value, (int, float)) and not isinstance(value, bool) and any(
        k in low for k in ("pnl", "return", "sharpe", "sentiment", "score", "decay", "drawdown")
    ):
        return _Hue.GREEN if value > 0 else _Hue.RED if value < 0 else _Hue.GREY
    return None


def _cell(key, value) -> str:
    color = _color_for(key, value)
    text = _plain(value)
    return _c(text, color) if color else text


def _box(title: str, body: str) -> str:
    """Wrap multi-line body in a box with a colored title header."""
    lines = body.split("\n")
    inner = max([_dwidth(title) + 1, *(_dwidth(ln) for ln in lines)])
    g, bx = _Hue.GREY, _BOX
    top = (_c(bx["tl"] + bx["h"] + " ", g) + _c(title, _Hue.B + _Hue.ACCENT)
           + _c(" " + bx["h"] * max(0, inner - _dwidth(title) - 1) + bx["tr"], g))
    mid = "\n".join(_c(bx["v"] + " ", g) + _pad(ln, inner) + _c(" " + bx["v"], g)
                    for ln in lines)
    bot = _c(bx["bl"] + bx["h"] * (inner + 2) + bx["br"], g)
    return f"{top}\n{mid}\n{bot}"


def _table(rows: list[dict]) -> str:
    cols = list({k: None for r in rows for k in r})  # union, order-preserving
    widths = {c: max(_dwidth(c), *(_dwidth(_plain(r.get(c))) for r in rows)) for c in cols}
    head = "  ".join(_c(_pad(c, widths[c]), _Hue.B + _Hue.LABEL) for c in cols)
    sep = _c("  ".join("─" * widths[c] for c in cols), _Hue.GREY)
    body = []
    for r in rows:
        cells = [_pad(_cell(c, r.get(c)), widths[c]) for c in cols]
        body.append("  ".join(cells))
    return "\n".join([head, sep, *body])


def _kv(obj: dict) -> str:
    width = max((_dwidth(str(k)) for k in obj), default=0)
    lines = []
    for k, v in obj.items():
        label = _c(_pad(str(k), width), _Hue.LABEL)
        if isinstance(v, list) and len(v) >= 2 and all(isinstance(x, (int, float)) for x in v):
            val = f"{_sparkline(v)} {_c(_plain(v[-1]), _Hue.DIM)}"
        elif isinstance(v, (dict, list)):
            blob = json.dumps(v, default=str, ensure_ascii=False)
            val = _c(blob if len(blob) <= 72 else blob[:69] + "…", _Hue.GREY)
        else:
            val = _cell(k, v)
        lines.append(f"{label}  {val}")
    return "\n".join(lines)


def _print(obj) -> None:
    """Pretty in a terminal; JSON when piped or with --json (machine-safe)."""
    if _FORCE_JSON or not _COLOR:
        print(json.dumps(obj, indent=2, default=str))
        return
    title = _TITLE or "yammyquant"
    if isinstance(obj, list) and obj and all(isinstance(x, dict) for x in obj):
        print(_c(f"{title} ", _Hue.B + _Hue.ACCENT) + _c(f"({len(obj)} rows)", _Hue.GREY))
        print(_table(obj))
    elif isinstance(obj, dict):
        print(_box(title, _kv(obj)))
    elif isinstance(obj, list):
        print(_c(f"{title}", _Hue.B + _Hue.ACCENT))
        print("\n".join(f"  {_c('-', _Hue.ACCENT)} {x}" for x in obj)
              or _c("  (empty)", _Hue.GREY))
    else:
        print(obj)


def main(argv: Optional[list[str]] = None) -> int:
    """
    Parse and execute a YammyQuant operator CLI command.
    
    Parses global options (--state and --store) and the specified subcommand, then dispatches to the appropriate handler.
    
    Parameters:
        argv (list[str], optional): Arguments to parse; defaults to sys.argv if None.
    
    Returns:
        int: Exit code; 0 on success, 1 on argument validation error or unrecognized command.
    """
    parser = argparse.ArgumentParser(
        prog="yq", description=banner(),
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--state", default="yammyquant_state.db", help="SQLite state file")
    parser.add_argument("--store", default="data_store", help="DuckDB candle store dir")
    parser.add_argument("--json", action="store_true", help="raw JSON output (for piping)")
    sub = parser.add_subparsers(dest="cmd", required=False)

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

    p = sub.add_parser("news", help="collect/list news (RSS); operator judges sentiment")
    p.add_argument("symbol", nargs="?")
    p.add_argument("--collect", action="store_true", help="fetch feeds into the store")
    p.add_argument("--all", action="store_true", help="store untagged items too")

    p = sub.add_parser("brief", help="research digest (price+features+news+fundamentals)")
    p.add_argument("ticker")
    p.add_argument("--interval", default="1d")
    p.add_argument("--exchange", help="for stock fundamentals, e.g. kis")

    p = sub.add_parser("disclosures", help="DART (전자공시) filings for a corp_code")
    p.add_argument("corp_code")
    p.add_argument("--symbol", default="")

    p = sub.add_parser("optimize", help="grid-search strategy params (optionally walk-forward)")
    p.add_argument("ticker")
    p.add_argument("interval")
    p.add_argument("strategy")
    p.add_argument("--metric", default="sharpe")
    p.add_argument("--walk-forward", type=int, default=0, metavar="N",
                   help="number of walk-forward splits (0 = in-sample grid search)")

    p = sub.add_parser("strategies", help="list/toggle strategies & blend config")
    p.add_argument("--enable")
    p.add_argument("--disable")
    p.add_argument("--rule", choices=["any", "weighted", "majority", "unanimous"],
                   help="how `decide` blends signals across strategies")
    p.add_argument("--threshold", type=float, help="vote threshold for weighted/majority")
    p.add_argument("--weight", action="append", metavar="NAME=VAL",
                   help="per-strategy vote weight, e.g. --weight macross=2")

    p = sub.add_parser("ensemble", help="backtest a blend of strategies (voting/weighted)")
    p.add_argument("ticker")
    p.add_argument("interval")
    p.add_argument("--members", required=True,
                   help="comma list, e.g. macross,rsi_reversion,supertrend")
    p.add_argument("--weights", help="comma list of floats matching --members")
    p.add_argument("--rule", default="weighted",
                   choices=["any", "weighted", "majority", "unanimous"])
    p.add_argument("--threshold", type=float, default=0.5)
    p.add_argument("--cash", type=float, default=10_000.0)
    p.add_argument("--fee", type=float, default=0.001)

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
    p.add_argument("--importance", type=float, help="salience 1..10 for memory recall")
    p.add_argument("--limit", type=int, default=50)

    p = sub.add_parser("recall", help="session-start memory: ranked journal + inbox + positions")
    p.add_argument("query", nargs="?", help="optional topic to bias retrieval")
    p.add_argument("--limit", type=int, default=5)

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

    global _FORCE_JSON, _TITLE
    _FORCE_JSON = args.json
    _TITLE = args.cmd or ""
    if not args.cmd:                       # `yq` with no command → cute home screen
        print(banner())
        parser.print_help()
        return 0

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
                print("usage: yq config default <exchange>")
                return 1
            cfg = xcfg.load_config()
            cfg["default_exchange"] = args.args[0].lower()
            path = xcfg.save_config(cfg)
            _print({"default_exchange": args.args[0].lower(), "saved": str(path)})
        elif args.action == "set":
            if len(args.args) < 2 or any("=" not in a for a in args.args[1:]):
                print("usage: yq config set <exchange> field=value [field=value ...]")
                return 1
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

    if args.cmd == "news":
        if args.collect:
            _print(ops.collect_news(state, store_all=args.all))
        else:
            _print(state.news(symbol=args.symbol, limit=50))
        return 0

    if args.cmd == "brief":
        _print(ops.brief(DuckDBStore(args.store), state, args.ticker,
                        interval=args.interval, exchange=args.exchange))
        return 0

    if args.cmd == "disclosures":
        from yammyquant.feeds.dart import DartFeed
        items = DartFeed().disclosures(args.corp_code, symbol=args.symbol)
        for it in items:
            state.add_news(**it.as_record())
        _print([it.as_record() for it in items])
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
        if args.rule:
            state.set("ensemble_rule", args.rule)
        if args.threshold is not None:
            state.set("ensemble_threshold", args.threshold)
        for pair in (args.weight or []):
            name, _, val = pair.partition("=")
            state.set(f"strategy.{name.strip()}.weight", float(val))
        _print({"available": sorted(ops.STRATEGIES),
                "enabled": ops.enabled_strategies(state),
                "blend": {"rule": state.get("ensemble_rule", "any"),
                          "threshold": float(state.get("ensemble_threshold", 0.5)),
                          "weights": {n: state.get(f"strategy.{n}.weight", 1.0)
                                      for n in ops.STRATEGIES
                                      if state.get(f"strategy.{n}.weight") is not None}}})
        return 0

    if args.cmd == "ensemble":
        members = [s.strip() for s in args.members.split(",") if s.strip()]
        weights = [float(x) for x in args.weights.split(",")] if args.weights else None
        _print(ops.ensemble_backtest(DuckDBStore(args.store), args.ticker, args.interval,
                                     members, weights=weights, rule=args.rule,
                                     threshold=args.threshold, cash=args.cash, fee=args.fee,
                                     state=state))
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
                    print("usage: yq risk set field=value ...")
                    return 1
                field_name, value = assignment.split("=", 1)
                setattr(policy, field_name,
                        None if value.lower() in ("", "none") else float(value))
            policy.save(state)
        from dataclasses import asdict
        _print(asdict(AccountRiskPolicy.load(state)))
        return 0

    if args.cmd == "journal":
        if args.text:
            jid = state.add_journal(args.text, tag=args.tag, importance=args.importance)
            _print({"id": jid, "tag": args.tag, "importance": args.importance, "text": args.text})
        else:
            _print(state.journal(limit=args.limit))
        return 0

    if args.cmd == "recall":
        _print(ops.recall(state, query=args.query, limit=args.limit))
        return 0

    if args.cmd == "watch":
        if args.action == "add":
            if not args.symbol:
                print("usage: yq watch add SYMBOL [--exchange --interval --note]")
                return 1
            state.add_watch(args.symbol, args.exchange, args.interval, args.note)
        elif args.action == "rm":
            if not args.symbol:
                print("usage: yq watch rm SYMBOL")
                return 1
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
                    print("usage: yq target SYMBOL=weight ...")
                    return 1
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
