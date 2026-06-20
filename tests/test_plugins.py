"""Self-improvement plugin system: scaffold → auto-load → use."""

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from yammyquant.data.candle import Candle
from yammyquant.data import indicators as ind
from yammyquant.backtest.engine import Backtest
from yammyquant.ops import operator as ops
from yammyquant import plugins


@pytest.fixture
def clean_registries():
    """Snapshot the global registries and restore them after each test."""
    strat = dict(ops.STRATEGIES)
    grids = dict(ops.DEFAULT_GRIDS)
    reg = dict(ind.REGISTRY)
    yield
    ops.STRATEGIES.clear()
    ops.STRATEGIES.update(strat)
    ops.DEFAULT_GRIDS.clear()
    ops.DEFAULT_GRIDS.update(grids)
    ind.REGISTRY.clear()
    ind.REGISTRY.update(reg)


def _candle(n=120):
    idx = pd.date_range("2023-01-01", periods=n, freq="1D")
    close = 100 + 10 * np.sin(np.arange(n) / 7.0)
    df = pd.DataFrame({"open": close, "high": close + 1, "low": close - 1,
                       "close": close, "volume": np.full(n, 1000.0)}, index=idx)
    return Candle("TESTUSDT", df, interval="1d")


def test_slug_and_camel():
    assert plugins._slug("My Cool Edge!") == "my_cool_edge"
    assert plugins._camel("my_cool_edge") == "MyCoolEdge"
    with pytest.raises(ValueError):
        plugins._slug("123")


def test_scaffold_strategy_loads_and_backtests(tmp_path, clean_registries):
    path = plugins.new_plugin("strategy", "my_edge", base=tmp_path)
    assert path.exists() and path.name == "my_edge.py"

    out = plugins.load_plugins(base=tmp_path)
    assert "my_edge" in out["strategies"]
    assert not out["errors"]
    assert "my_edge" in ops.STRATEGIES

    # the freshly scaffolded strategy is immediately usable
    result = Backtest(_candle(), ops.STRATEGIES["my_edge"](), cash=10_000).run()
    assert "sharpe" in result.stats


def test_scaffold_indicator_loads_and_runs(tmp_path, clean_registries):
    plugins.new_plugin("indicator", "my_signal", base=tmp_path)
    out = plugins.load_plugins(base=tmp_path)
    assert "my_signal" in out["indicators"]
    series = _candle().ind.my_signal(10)
    assert len(series) == len(_candle())


def test_scaffold_skill(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    path = plugins.new_plugin("skill", "Morning Routine")
    assert path == Path(".claude/skills/morning_routine/SKILL.md")
    assert (tmp_path / path).exists()
    text = path.read_text()
    assert "name: morning_routine" in text and "When to use" in text


def test_duplicate_scaffold_refused(tmp_path, clean_registries):
    plugins.new_plugin("strategy", "dup", base=tmp_path)
    with pytest.raises(FileExistsError):
        plugins.new_plugin("strategy", "dup", base=tmp_path)


def test_broken_plugin_reported_not_raised(tmp_path, clean_registries):
    d = tmp_path / "strategies"
    d.mkdir(parents=True)
    (d / "bad.py").write_text("this is not valid python :(\n")
    out = plugins.load_plugins(base=tmp_path)
    assert out["errors"] and "bad.py" in out["errors"][0]
    # a broken file doesn't abort loading
    assert "strategies" in out


def test_load_missing_dir_is_safe(tmp_path, clean_registries):
    out = plugins.load_plugins(base=tmp_path / "nope")
    assert out["strategies"] == [] and out["errors"] == []
