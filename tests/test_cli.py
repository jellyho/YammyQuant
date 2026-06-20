"""CLI presentation logic — pretty rendering vs machine-safe JSON."""

import io
import json
from contextlib import redirect_stdout

import yammyquant.ops.cli as cli


def _capture(obj, color, force_json=False, title="yq"):
    old_c, old_j, old_t = cli._COLOR, cli._FORCE_JSON, cli._TITLE
    cli._COLOR, cli._FORCE_JSON, cli._TITLE = color, force_json, title
    try:
        buf = io.StringIO()
        with redirect_stdout(buf):
            cli._print(obj)
        return buf.getvalue()
    finally:
        cli._COLOR, cli._FORCE_JSON, cli._TITLE = old_c, old_j, old_t


def test_print_json_when_not_a_terminal():
    out = _capture({"a": 1, "rows": [{"x": 1}]}, color=False)
    assert json.loads(out) == {"a": 1, "rows": [{"x": 1}]}


def test_print_force_json_overrides_color():
    out = _capture({"a": 1}, color=True, force_json=True)
    assert json.loads(out) == {"a": 1}


def test_dict_with_one_list_of_dicts_renders_as_table():
    # leaderboard-shaped payload: scalars in a box + the list as a table,
    # not a truncated JSON blob.
    payload = {"ticker": "BTCUSDT", "metric": "sharpe",
               "ranking": [{"strategy": "macross", "sharpe": 1.2},
                           {"strategy": "donchian_breakout", "sharpe": 0.4}]}
    out = _capture(payload, color=True)
    assert "ranking " in out and "(2 rows)" in out      # table title
    assert "macross" in out and "donchian_breakout" in out
    assert "strategy" in out                            # column header
    # the row data is not dumped as a JSON blob
    assert '"strategy"' not in out


def test_dict_without_list_of_dicts_uses_kv_box():
    out = _capture({"realized_pnl": 100.0, "closed_trades": 2}, color=True)
    assert "realized_pnl" in out and "closed_trades" in out


def test_empty_list_value_does_not_trigger_table():
    # attribution with no round-trips: by_strategy is [] -> stays a kv box
    out = _capture({"by_strategy": []}, color=True)
    assert "by_strategy" in out and "(0 rows)" not in out
