import numpy as np
import pandas as pd
import pytest

pytest.importorskip("gymnasium")

from yammyquant.data.candle import Candle
from yammyquant.data.sources.store import DuckDBStore
from yammyquant.ops.training import build_env


def _seed(tmp_path, n=300):
    store = DuckDBStore(tmp_path / "store")
    idx = pd.date_range("2023-01-01", periods=n, freq="1D")
    close = 100 + 5 * np.sin(np.arange(n) / 6.0) + np.arange(n) * 0.05
    df = pd.DataFrame(
        {"open": close, "high": close + 1, "low": close - 1, "close": close,
         "volume": [1000.0] * n},
        index=idx,
    )
    store.write(Candle("BTCUSDT", df, interval="1d"))
    return store


def test_build_env_from_store(tmp_path):
    store = _seed(tmp_path)
    env = build_env(store, "BTCUSDT", "1d", window=10, episode_length=50)
    obs, info = env.reset(seed=0)
    assert obs.shape == (11,)
    obs, reward, terminated, truncated, info = env.step(env.action_space.sample())
    assert obs.shape == (11,)
    assert isinstance(reward, float)


def test_train_saves_checkpoint(tmp_path):
    pytest.importorskip("stable_baselines3")
    from yammyquant.ops.training import train
    from yammyquant.state.store import LiveState
    import os

    store = _seed(tmp_path)
    state = LiveState(tmp_path / "s.db")
    result = train(store, "BTCUSDT", "1d", timesteps=200, algo="PPO",
                   models_dir=tmp_path / "models", episode_length=50, state=state)
    assert os.path.exists(result["checkpoint"])
    assert any(a["kind"] == "train" for a in state.activity())
