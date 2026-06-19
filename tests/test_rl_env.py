import numpy as np
import pytest

gym = pytest.importorskip("gymnasium")

from yammyquant.rl.env import ChartFollowingEnv


def _closes(n=200):
    t = np.arange(n)
    return 100 + 5 * np.sin(t / 6.0)


def test_reset_returns_obs_and_info():
    env = ChartFollowingEnv(_closes(), window=10, seed=0)
    obs, info = env.reset(seed=0)
    assert obs.shape == (11,)
    assert isinstance(info, dict)


def test_step_returns_five_tuple():
    env = ChartFollowingEnv(_closes(), window=10, seed=0)
    env.reset(seed=0)
    action = env.action_space.sample()
    out = env.step(action)
    assert len(out) == 5
    obs, reward, terminated, truncated, info = out
    assert obs.shape == (11,)
    assert isinstance(reward, float)
    assert isinstance(terminated, bool)
    assert isinstance(truncated, bool)


def test_episode_terminates():
    env = ChartFollowingEnv(_closes(120), window=10, episode_length=50, seed=1)
    env.reset(seed=1)
    steps = 0
    done = False
    while not done and steps < 1000:
        _, _, terminated, truncated, _ = env.step(env.action_space.sample())
        done = terminated or truncated
        steps += 1
    assert done


def test_from_candle(sine_candle):
    env = ChartFollowingEnv.from_candle(sine_candle, window=10)
    obs, _ = env.reset()
    assert obs.shape == (11,)
