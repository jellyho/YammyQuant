from yammyquant.state.store import LiveState


def test_journal_add_and_list(tmp_path):
    s = LiveState(tmp_path / "s.db")
    jid = s.add_journal("BTC thesis: trend intact above 20d MA", tag="thesis")
    rows = s.journal()
    assert rows[0]["id"] == jid
    assert rows[0]["tag"] == "thesis"
    assert "thesis" in rows[0]["text"]


def test_watchlist_add_update_remove(tmp_path):
    s = LiveState(tmp_path / "s.db")
    s.add_watch("BTCUSDT", "binance", "1d", note="majors")
    s.add_watch("KRW-BTC", "upbit", "1h")
    wl = {w["symbol"]: w for w in s.watchlist()}
    assert wl["BTCUSDT"]["exchange"] == "binance" and wl["BTCUSDT"]["note"] == "majors"
    assert wl["KRW-BTC"]["interval"] == "1h"

    s.add_watch("BTCUSDT", "binance", "4h")  # upsert interval
    assert {w["symbol"]: w["interval"] for w in s.watchlist()}["BTCUSDT"] == "4h"

    s.remove_watch("BTCUSDT")
    assert [w["symbol"] for w in s.watchlist()] == ["KRW-BTC"]


def test_snapshot_includes_journal_and_watchlist(tmp_path):
    s = LiveState(tmp_path / "s.db")
    s.add_journal("note")
    s.add_watch("BTCUSDT")
    snap = s.snapshot()
    assert "journal" in snap and "watchlist" in snap
    assert snap["journal"][0]["text"] == "note"
