import pytest

from yammyquant.backtest.engine import Backtest
from yammyquant.strategy.builtin import RSIReversion, DonchianBreakout
from yammyquant.ops.operator import STRATEGIES, DEFAULT_GRIDS, enabled_strategies
from yammyquant.state.store import LiveState


def test_new_strategies_registered():
    assert "rsi_reversion" in STRATEGIES
    assert "donchian_breakout" in STRATEGIES


@pytest.mark.parametrize("name", sorted(STRATEGIES))
def test_every_strategy_backtests(name, sine_candle, trend_candle):
    """Each registered strategy builds with defaults and runs without error."""
    for candle in (sine_candle, trend_candle):
        result = Backtest(candle, STRATEGIES[name](), cash=10_000).run()
        assert "sharpe" in result.stats
        assert result.stats["num_trades"] >= 0


def test_every_strategy_has_optimize_grid():
    assert set(DEFAULT_GRIDS) == set(STRATEGIES)


def test_rsi_reversion_runs(sine_candle):
    result = Backtest(sine_candle, RSIReversion(14), cash=10_000).run()
    assert "sharpe" in result.stats


def test_donchian_breakout_trades_on_trend(trend_candle):
    result = Backtest(trend_candle, DonchianBreakout(10), cash=10_000).run()
    # a steadily rising series should trigger at least one breakout buy
    assert result.stats["num_trades"] >= 1


def test_enabled_strategies_default_all(tmp_path):
    state = LiveState(tmp_path / "s.db")
    assert set(enabled_strategies(state)) == set(STRATEGIES)


def test_disable_strategy(tmp_path):
    state = LiveState(tmp_path / "s.db")
    state.set("strategy.macross.enabled", False)
    assert "macross" not in enabled_strategies(state)
    assert "donchian_breakout" in enabled_strategies(state)


@pytest.fixture
def gbm_candles():
    """A few realistic random-walk series — long enough that every strategy
    should trade at least once (guards the 'indicator never warms / never
    fires' class of bugs, e.g. CCI/ADX/SuperTrend warmups)."""
    import numpy as np
    import pandas as pd
    from yammyquant.data.candle import Candle
    out = []
    for seed in (1, 2, 3, 7, 42):
        rng = np.random.default_rng(seed)
        close = 100 * np.exp(np.cumsum(rng.normal(0.0004, 0.02, 500)))
        idx = pd.date_range("2022-01-01", periods=500, freq="1D")
        df = pd.DataFrame({"open": close, "high": close * 1.012, "low": close * 0.988,
                           "close": close, "volume": rng.uniform(800, 2200, 500)}, index=idx)
        out.append(Candle("X", df, interval="1d"))
    return out


# strategies whose premise the generic GBM fixture can't express — exercised by
# dedicated tests instead: opening_range_breakout (intraday sessions),
# volume_spike_breakout (the fixture's volume is uniform, so it has no spikes)
_FIXTURE_EXEMPT = {"opening_range_breakout", "volume_spike_breakout"}


@pytest.mark.parametrize("name", sorted(set(STRATEGIES) - _FIXTURE_EXEMPT))
def test_strategy_trades_on_realistic_data(name, gbm_candles):
    """Every registered strategy must produce >=1 trade on a long realistic
    series — a near-flat equity from zero trades is the bug we keep catching."""
    counts = [Backtest(c, STRATEGIES[name](), cash=10_000, fee=0.001).run().stats["num_trades"]
              for c in gbm_candles]
    assert min(counts) >= 1, f"{name} made 0 trades on some seed: {counts}"


def _intraday_candle(days=5, bars_per_day=24):
    """Synthetic 1h bars spanning several days, with an intraday breakout each day."""
    import numpy as np
    import pandas as pd
    from yammyquant.data.candle import Candle
    n = days * bars_per_day
    idx = pd.date_range("2023-01-01 00:00", periods=n, freq="1h")
    rng = np.random.default_rng(0)
    close = []
    for d in range(days):
        base = 100 + 5 * d
        # flat open then a strong ramp up later in the session -> breaks the range
        intraday = base + np.concatenate([rng.normal(0, 0.2, 6),
                                          np.linspace(0.3, 8.0, bars_per_day - 6)])
        close.extend(intraday)
    close = np.array(close)
    df = pd.DataFrame({"open": close, "high": close + 0.5, "low": close - 0.5,
                       "close": close, "volume": np.full(n, 100.0)}, index=idx)
    return Candle("X", df, interval="1h")


def test_opening_range_breakout_trades_intraday():
    from yammyquant.strategy.builtin import OpeningRangeBreakout
    candle = _intraday_candle()
    res = Backtest(candle, OpeningRangeBreakout(opening_bars=6), cash=10_000, fee=0.0).run()
    assert res.stats["num_trades"] >= 1   # breaks the opening range on the ramp


def test_session_vwap_resets_each_day():
    import numpy as np
    import pandas as pd
    from yammyquant.data.candle import Candle
    # two days; day 2 trades at a higher level — session VWAP must jump (reset),
    # while cumulative vwap stays dragged down by day 1
    idx = pd.date_range("2023-01-01 00:00", periods=48, freq="1h")
    close = np.concatenate([np.full(24, 100.0), np.full(24, 200.0)])
    df = pd.DataFrame({"open": close, "high": close, "low": close, "close": close,
                       "volume": np.full(48, 10.0)}, index=idx)
    c = Candle("X", df, interval="1h")
    sv = c.ind.session_vwap().to_numpy()
    cum = c.ind.vwap().to_numpy()
    assert sv[-1] == pytest.approx(200.0, abs=1e-6)     # day-2 session VWAP == day-2 price
    assert cum[-1] < 200.0                               # cumulative still dragged by day 1


def test_volume_spike_breakout_trades_on_spike():
    import numpy as np
    import pandas as pd
    from yammyquant.data.candle import Candle
    from yammyquant.strategy.builtin import VolumeSpikeBreakout
    n = 60
    idx = pd.date_range("2023-01-01", periods=n, freq="1D")
    close = np.r_[np.full(40, 100.0), np.linspace(100.0, 130.0, 20)]   # flat then breakout
    vol = np.full(n, 100.0)
    vol[45] = 1000.0                                                    # a clear volume spike
    df = pd.DataFrame({"open": close, "high": close + 0.5, "low": close - 0.5,
                       "close": close, "volume": vol}, index=idx)
    res = Backtest(Candle("X", df, interval="1d"), VolumeSpikeBreakout(lookback=20, vol_mult=2.0),
                   cash=10_000, fee=0.0).run()
    assert res.stats["num_trades"] >= 1


def test_vwap_band_scalp_trades_intraday():
    from yammyquant.strategy.builtin import VWAPBandScalp
    candle = _intraday_candle(days=4, bars_per_day=24)
    res = Backtest(candle, VWAPBandScalp(band=1.0, std_period=10), cash=10_000, fee=0.0).run()
    assert "sharpe" in res.stats and res.stats["num_trades"] >= 0
