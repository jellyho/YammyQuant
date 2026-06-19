"""Agent memory: importance-weighted journal + recall (memory stream)."""

from datetime import datetime, timezone, timedelta

from yammyquant.state.store import LiveState
from yammyquant.ops import operator as ops


def test_journal_importance_stored(tmp_path):
    s = LiveState(tmp_path / "s.db")
    jid = s.add_journal("scaled into BTC on breakout", tag="thesis", importance=8)
    row = next(j for j in s.journal() if j["id"] == jid)
    assert row["importance"] == 8


def test_migration_adds_columns(tmp_path):
    db = tmp_path / "old.db"
    import sqlite3
    # simulate a pre-memory DB without the importance/accessed columns
    con = sqlite3.connect(db)
    con.executescript("CREATE TABLE journal (id INTEGER PRIMARY KEY AUTOINCREMENT,"
                      " ts TEXT NOT NULL, tag TEXT, text TEXT NOT NULL);")
    con.execute("INSERT INTO journal (ts, tag, text) VALUES ('2024-01-01T00:00:00+00:00','t','old note')")
    con.commit(); con.close()
    s = LiveState(db)                       # __init__ runs the migration
    assert s.add_journal("new", importance=5)  # importance column now exists
    assert all(k in s.journal()[0] for k in ("importance", "accessed"))


def test_recall_ranks_importance_and_relevance(tmp_path):
    s = LiveState(tmp_path / "s.db")
    s.add_journal("bought ETH after the merge upgrade", tag="thesis", importance=9)
    s.add_journal("random note about coffee", tag="misc", importance=1)
    s.add_journal("BTC stop-loss rationale at 60k", tag="risk", importance=7)

    # no query -> recency×importance; high-importance entries surface
    out = ops.recall(s, limit=2)
    ids_text = " ".join(m["text"] for m in out["memories"])
    assert "coffee" not in ids_text                 # low importance drops out
    assert out["memories"][0]["score"] >= out["memories"][-1]["score"]

    # query -> relevance biases toward the matching memory
    q = ops.recall(s, query="ETH merge", limit=3)
    assert q["memories"][0]["text"].startswith("bought ETH")
    assert all(m["text"] != "random note about coffee" for m in q["memories"])


def test_recall_bundles_inbox_and_positions(tmp_path):
    s = LiveState(tmp_path / "s.db")
    s.post_instruction("rotate 20% into KR stocks")
    s.upsert_position("BTCUSDT", 0.5, 60000)
    s.add_journal("note", importance=5)
    out = ops.recall(s)
    assert out["unread_inbox"] and out["unread_inbox"][0]["message"].startswith("rotate")
    assert out["open_positions"][0]["ticker"] == "BTCUSDT"


def test_recall_bumps_access_counter(tmp_path):
    s = LiveState(tmp_path / "s.db")
    jid = s.add_journal("recalled memory", importance=6)
    ops.recall(s)
    ops.recall(s)
    row = next(j for j in s.journal() if j["id"] == jid)
    assert row["accessed"] == 2
