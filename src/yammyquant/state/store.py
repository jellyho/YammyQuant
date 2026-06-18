"""Shared live-state store backed by SQLite.

This is the cockpit's source of truth — the single place that both the
**operator** (Claude Code, running the CLI toolbelt) and the **dashboard**
(FastAPI) read from and write to. SQLite in WAL mode handles concurrent access
from those two separate processes cleanly, with no server to run.

Tables
------
- ``positions``   : current holdings per ticker (qty, avg price)
- ``trades``      : trade log; live orders sit in ``pending`` until approved
- ``equity``      : equity-curve snapshots over time
- ``signals``     : latest strategy signals awaiting action
- ``activity``    : append-only log of what the operator did (shown live)
- ``inbox``       : instructions the user leaves for the operator to read
- ``settings``    : key/value config (e.g. strategy on/off, live-trading flag)

Everything is JSON-friendly dicts so the web layer can serialize directly.
"""

from __future__ import annotations

import json
import sqlite3
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional

_SCHEMA = """
CREATE TABLE IF NOT EXISTS positions (
    ticker      TEXT PRIMARY KEY,
    quantity    REAL NOT NULL DEFAULT 0,
    avg_price   REAL NOT NULL DEFAULT 0,
    updated_at  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS trades (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ts          TEXT NOT NULL,
    ticker      TEXT NOT NULL,
    side        TEXT NOT NULL,            -- BUY / SELL
    quantity    REAL NOT NULL,
    price       REAL,
    mode        TEXT NOT NULL,            -- paper / live
    status      TEXT NOT NULL,            -- pending / filled / rejected / cancelled
    rationale   TEXT,
    meta        TEXT                      -- JSON blob
);
CREATE TABLE IF NOT EXISTS equity (
    ts          TEXT NOT NULL,
    equity      REAL NOT NULL,
    cash        REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS signals (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ts          TEXT NOT NULL,
    ticker      TEXT NOT NULL,
    strategy    TEXT NOT NULL,
    action      TEXT NOT NULL,
    strength    REAL,
    meta        TEXT
);
CREATE TABLE IF NOT EXISTS activity (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ts          TEXT NOT NULL,
    kind        TEXT NOT NULL,            -- collect / backtest / train / trade / note ...
    summary     TEXT NOT NULL,
    meta        TEXT
);
CREATE TABLE IF NOT EXISTS inbox (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ts          TEXT NOT NULL,
    message     TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'unread'   -- unread / read
);
CREATE TABLE IF NOT EXISTS settings (
    key         TEXT PRIMARY KEY,
    value       TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS journal (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ts          TEXT NOT NULL,
    tag         TEXT,
    text        TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS watchlist (
    symbol      TEXT PRIMARY KEY,
    exchange    TEXT,
    interval    TEXT,
    note        TEXT,
    added_at    TEXT NOT NULL
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class LiveState:
    """SQLite-backed cockpit state shared by the operator and the dashboard."""

    def __init__(self, path: str | Path = "yammyquant_state.db"):
        self.path = str(path)
        with self._conn() as c:
            c.executescript(_SCHEMA)

    @contextmanager
    def _conn(self):
        conn = sqlite3.connect(self.path, timeout=30.0)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA busy_timeout=30000")
            yield conn
            conn.commit()
        finally:
            conn.close()

    # -- activity log ------------------------------------------------------
    def log(self, kind: str, summary: str, **meta: Any) -> None:
        with self._conn() as c:
            c.execute(
                "INSERT INTO activity (ts, kind, summary, meta) VALUES (?,?,?,?)",
                (_now(), kind, summary, json.dumps(meta) if meta else None),
            )

    def activity(self, limit: int = 100) -> list[dict]:
        return self._fetch(
            "SELECT * FROM activity ORDER BY id DESC LIMIT ?", (limit,)
        )

    # -- positions ---------------------------------------------------------
    def upsert_position(self, ticker: str, quantity: float, avg_price: float) -> None:
        with self._conn() as c:
            if quantity <= 1e-12:
                c.execute("DELETE FROM positions WHERE ticker=?", (ticker,))
            else:
                c.execute(
                    "INSERT INTO positions (ticker, quantity, avg_price, updated_at) "
                    "VALUES (?,?,?,?) ON CONFLICT(ticker) DO UPDATE SET "
                    "quantity=excluded.quantity, avg_price=excluded.avg_price, "
                    "updated_at=excluded.updated_at",
                    (ticker, quantity, avg_price, _now()),
                )

    def positions(self) -> list[dict]:
        return self._fetch("SELECT * FROM positions ORDER BY ticker")

    # -- trades ------------------------------------------------------------
    def add_trade(
        self,
        ticker: str,
        side: str,
        quantity: float,
        price: Optional[float],
        mode: str,
        status: str,
        rationale: str = "",
        **meta: Any,
    ) -> int:
        with self._conn() as c:
            cur = c.execute(
                "INSERT INTO trades (ts, ticker, side, quantity, price, mode, status, rationale, meta)"
                " VALUES (?,?,?,?,?,?,?,?,?)",
                (_now(), ticker, side, quantity, price, mode, status, rationale,
                 json.dumps(meta) if meta else None),
            )
            return int(cur.lastrowid)

    def set_trade_status(self, trade_id: int, status: str) -> None:
        with self._conn() as c:
            c.execute("UPDATE trades SET status=? WHERE id=?", (status, trade_id))

    def set_trade_meta(self, trade_id: int, **fields: Any) -> None:
        """Merge ``fields`` into a trade's JSON meta (realized PnL, order id, …)."""
        current = self.get_trade(trade_id)
        meta = current.get("meta") if current else None
        meta = meta if isinstance(meta, dict) else {}
        meta.update(fields)
        with self._conn() as c:
            c.execute("UPDATE trades SET meta=? WHERE id=?", (json.dumps(meta), trade_id))

    def record_realized(self, trade_id: int, realized: float) -> None:
        """Store realized PnL on a (sell) trade's meta — used by risk/reporting."""
        self.set_trade_meta(trade_id, realized=realized)

    def open_orders(self) -> list[dict]:
        """Live orders that have been submitted to an exchange but not yet settled."""
        return self.trades(status="submitted")

    def trades(self, limit: int = 200, status: Optional[str] = None) -> list[dict]:
        if status:
            return self._fetch(
                "SELECT * FROM trades WHERE status=? ORDER BY id DESC LIMIT ?",
                (status, limit),
            )
        return self._fetch("SELECT * FROM trades ORDER BY id DESC LIMIT ?", (limit,))

    def get_trade(self, trade_id: int) -> Optional[dict]:
        rows = self._fetch("SELECT * FROM trades WHERE id=?", (trade_id,))
        return rows[0] if rows else None

    # -- equity ------------------------------------------------------------
    def record_equity(self, equity: float, cash: float) -> None:
        with self._conn() as c:
            c.execute(
                "INSERT INTO equity (ts, equity, cash) VALUES (?,?,?)",
                (_now(), equity, cash),
            )

    def equity_curve(self, limit: int = 1000) -> list[dict]:
        rows = self._fetch("SELECT * FROM equity ORDER BY ts DESC LIMIT ?", (limit,))
        return list(reversed(rows))

    # -- signals -----------------------------------------------------------
    def add_signal(self, ticker: str, strategy: str, action: str,
                   strength: float = 0.0, **meta: Any) -> None:
        with self._conn() as c:
            c.execute(
                "INSERT INTO signals (ts, ticker, strategy, action, strength, meta)"
                " VALUES (?,?,?,?,?,?)",
                (_now(), ticker, strategy, action, strength,
                 json.dumps(meta) if meta else None),
            )

    def signals(self, limit: int = 100) -> list[dict]:
        return self._fetch("SELECT * FROM signals ORDER BY id DESC LIMIT ?", (limit,))

    # -- inbox -------------------------------------------------------------
    def post_instruction(self, message: str) -> int:
        with self._conn() as c:
            cur = c.execute(
                "INSERT INTO inbox (ts, message) VALUES (?,?)", (_now(), message)
            )
            return int(cur.lastrowid)

    def inbox(self, only_unread: bool = False) -> list[dict]:
        if only_unread:
            return self._fetch(
                "SELECT * FROM inbox WHERE status='unread' ORDER BY id"
            )
        return self._fetch("SELECT * FROM inbox ORDER BY id DESC LIMIT 200")

    def mark_inbox_read(self, ids: Iterable[int]) -> None:
        ids = list(ids)
        if not ids:
            return
        with self._conn() as c:
            c.executemany("UPDATE inbox SET status='read' WHERE id=?", [(i,) for i in ids])

    # -- settings ----------------------------------------------------------
    def set(self, key: str, value: Any) -> None:
        with self._conn() as c:
            c.execute(
                "INSERT INTO settings (key, value) VALUES (?,?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, json.dumps(value)),
            )

    def get(self, key: str, default: Any = None) -> Any:
        rows = self._fetch("SELECT value FROM settings WHERE key=?", (key,))
        return json.loads(rows[0]["value"]) if rows else default

    def settings(self) -> dict:
        return {r["key"]: json.loads(r["value"]) for r in self._fetch("SELECT * FROM settings")}

    # -- journal -----------------------------------------------------------
    def add_journal(self, text: str, tag: str = "") -> int:
        with self._conn() as c:
            cur = c.execute("INSERT INTO journal (ts, tag, text) VALUES (?,?,?)",
                            (_now(), tag, text))
            return int(cur.lastrowid)

    def journal(self, limit: int = 100) -> list[dict]:
        return self._fetch("SELECT * FROM journal ORDER BY id DESC LIMIT ?", (limit,))

    # -- watchlist ---------------------------------------------------------
    def add_watch(self, symbol: str, exchange: str = "", interval: str = "1d",
                  note: str = "") -> None:
        with self._conn() as c:
            c.execute(
                "INSERT INTO watchlist (symbol, exchange, interval, note, added_at) "
                "VALUES (?,?,?,?,?) ON CONFLICT(symbol) DO UPDATE SET "
                "exchange=excluded.exchange, interval=excluded.interval, note=excluded.note",
                (symbol, exchange, interval, note, _now()),
            )

    def remove_watch(self, symbol: str) -> None:
        with self._conn() as c:
            c.execute("DELETE FROM watchlist WHERE symbol=?", (symbol,))

    def watchlist(self) -> list[dict]:
        return self._fetch("SELECT * FROM watchlist ORDER BY symbol")

    # -- snapshot ----------------------------------------------------------
    def snapshot(self) -> dict:
        """Full cockpit state for the dashboard (one call → one render)."""
        return {
            "ts": _now(),
            "positions": self.positions(),
            "trades": self.trades(limit=100),
            "pending_trades": self.trades(status="pending"),
            "equity": self.equity_curve(),
            "signals": self.signals(limit=50),
            "activity": self.activity(limit=100),
            "inbox": self.inbox(),
            "settings": self.settings(),
            "journal": self.journal(limit=50),
            "watchlist": self.watchlist(),
        }

    # -- helpers -----------------------------------------------------------
    def _fetch(self, query: str, params: tuple = ()) -> list[dict]:
        with self._conn() as c:
            rows = c.execute(query, params).fetchall()
            out = []
            for r in rows:
                d = dict(r)
                if "meta" in d and d["meta"]:
                    try:
                        d["meta"] = json.loads(d["meta"])
                    except (TypeError, ValueError):
                        pass
                out.append(d)
            return out
