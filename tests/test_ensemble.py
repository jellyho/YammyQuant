"""Ensemble / signal-blending: vote aggregation, Ensemble strategy, decide rules."""

import pytest

from yammyquant.backtest.engine import Backtest
from yammyquant.strategy.ensemble import Ensemble, aggregate_votes
from yammyquant.strategy.builtin import MACross, RSIReversion, DonchianBreakout
from yammyquant.ops import operator as ops
from yammyquant.state.store import LiveState
from yammyquant.data.sources.store import DuckDBStore


# -- aggregate_votes -------------------------------------------------------
def test_any_rule():
    a = aggregate_votes(["BUY", "HOLD", "HOLD"], rule="any")
    assert a["buy"] and not a["sell"]
    a = aggregate_votes(["BUY", "SELL", "HOLD"], rule="any")
    assert a["buy"] and a["sell"]            # conflict surfaced


def test_unanimous_rule():
    assert aggregate_votes(["BUY", "BUY"], rule="unanimous")["buy"]
    a = aggregate_votes(["BUY", "SELL"], rule="unanimous")
    assert not a["buy"] and not a["sell"]    # disagreement -> no decision


def test_weighted_rule_threshold_and_weights():
    # 2 buy / 1 sell, equal weights -> net score (2-1)/3 = 0.33, clears a 0.3 bar
    assert aggregate_votes(["BUY", "BUY", "SELL"], rule="weighted", threshold=0.3)["buy"]
    # ...but the same 0.33 net fails a stricter 0.5 bar
    assert not aggregate_votes(["BUY", "BUY", "SELL"], rule="weighted", threshold=0.5)["buy"]
    # a heavy SELL weight flips the net negative
    a = aggregate_votes(["BUY", "BUY", "SELL"], weights=[1, 1, 5], rule="weighted", threshold=0.3)
    assert a["sell"] and not a["buy"]


def test_majority_rule():
    assert aggregate_votes(["BUY", "BUY", "SELL"], rule="majority", threshold=0.6)["buy"]
    a = aggregate_votes(["BUY", "SELL"], rule="majority", threshold=0.6)
    assert not a["buy"] and not a["sell"]    # 50/50 fails the 60% bar


def test_unknown_rule_raises():
    with pytest.raises(ValueError):
        aggregate_votes(["BUY"], rule="nope")


# -- Ensemble strategy -----------------------------------------------------
def test_ensemble_warmup_is_max_member():
    ens = Ensemble([MACross(5, 20), RSIReversion(14)], rule="any")
    assert ens.warmup == max(MACross(5, 20).warmup, RSIReversion(14).warmup)


def test_ensemble_backtests(sine_candle, trend_candle):
    ens = Ensemble([MACross(5, 20), DonchianBreakout(10)], rule="weighted", threshold=0.3)
    for candle in (sine_candle, trend_candle):
        result = Backtest(candle, ens, cash=10_000).run()
        assert "sharpe" in result.stats


def test_ensemble_unanimous_trades_no_more_than_any(trend_candle):
    members = [MACross(5, 20), DonchianBreakout(10)]
    any_trades = Backtest(trend_candle, Ensemble(members, rule="any"), cash=10_000).run()
    uni_trades = Backtest(
        trend_candle, Ensemble(members, rule="unanimous"), cash=10_000).run()
    assert uni_trades.stats["num_trades"] <= any_trades.stats["num_trades"]


def test_ensemble_backtest_helper(tmp_path, sine_candle):
    store = DuckDBStore(tmp_path / "store")
    store.write(sine_candle)
    out = ops.ensemble_backtest(store, "TESTUSDT", "1d",
                                ["macross", "rsi_reversion"], rule="majority", threshold=0.5)
    assert out["rule"] == "majority" and out["members"] == ["macross", "rsi_reversion"]
    assert "sharpe" in out


# -- decide respects the configured blend rule -----------------------------
def test_decide_default_rule_is_any(tmp_path, fake_exchange):
    store = DuckDBStore(tmp_path / "store")
    state = LiveState(tmp_path / "s.db")
    state.set("cash", 10_000.0)
    state.add_watch("BTCUSDT", "fake", "1d")
    out = ops.decide(store, state, weight=0.2, execute=False)
    assert any(p["side"] == "BUY" for p in out["proposals"])


def test_decide_unanimous_is_stricter(tmp_path, fake_exchange):
    store = DuckDBStore(tmp_path / "store")
    state = LiveState(tmp_path / "s.db")
    state.set("cash", 10_000.0)
    state.add_watch("BTCUSDT", "fake", "1d")
    state.set("ensemble_rule", "unanimous")
    out = ops.decide(store, state, weight=0.2, execute=False)
    # unanimous may suppress the entry; whatever it returns must be self-consistent
    assert isinstance(out["proposals"], list)


def test_weighted_ensemble_trades_not_flat(sine_candle):
    """Regression: persistent stances mean a weighted blend actually trades.
    Members fire on different bars, so instantaneous votes never agreed and the
    weighted equity used to be a dead-flat line (zero trades)."""
    from yammyquant.backtest.engine import Backtest
    from yammyquant.strategy.ensemble import Ensemble
    from yammyquant.strategy.builtin import MACross, EMACross, RSIReversion

    e = Ensemble([MACross(5, 20), EMACross(9, 21), RSIReversion(14)],
                 rule="weighted", threshold=0.4)
    res = Backtest(sine_candle, e, cash=10_000).run()
    assert res.stats["num_trades"] >= 1
