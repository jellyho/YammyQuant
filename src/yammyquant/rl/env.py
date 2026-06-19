"""Gymnasium environment for the "chart following" RL experiment.

This unifies the three near-identical legacy gym environments
(``ChartFollowing``, ``ChartFollowingDeploy``, ``ChartFollowingDeadend``) into a
single configurable :class:`ChartFollowingEnv`:

* ``deadend=False`` reproduces the original dense tracking reward.
* ``deadend=True`` reproduces the "deadend" variant that terminates the episode
  when the tracking error exceeds one standard deviation.

It targets the modern Gymnasium API (``reset`` returns ``(obs, info)`` and
``step`` returns the 5-tuple ``obs, reward, terminated, truncated, info``), so
it works with current Stable-Baselines3.

The env samples a random contiguous window from a provided close-price array on
each ``reset``, decoupling training from any live API. Use
:meth:`ChartFollowingEnv.from_candle` to build one from stored data.
"""

from __future__ import annotations

from typing import Optional

import numpy as np

try:
    import gymnasium as gym
    from gymnasium import spaces
except ImportError as exc:  # pragma: no cover - optional dependency
    raise ImportError("ChartFollowingEnv requires gymnasium. Install with: pip install 'yammyquant[rl]'") from exc


class ChartFollowingEnv(gym.Env):
    """Track the next price by adjusting a continuous position.

    Parameters
    ----------
    closes:
        1-D array of close prices to sample episodes from.
    window:
        Number of past closes in each observation (default 10).
    episode_length:
        Bars per episode. Defaults to spanning the whole series.
    deadend:
        If ``True``, terminate early when tracking error exceeds 1 std.
    """

    metadata = {"render_modes": []}

    def __init__(
        self,
        closes: np.ndarray,
        window: int = 10,
        episode_length: Optional[int] = None,
        deadend: bool = False,
        seed: Optional[int] = None,
    ):
        super().__init__()
        self.closes = np.asarray(closes, dtype=np.float64)
        if len(self.closes) <= window + 2:
            raise ValueError("Not enough price data for the requested window.")
        self.window = window
        self.episode_length = episode_length
        self.deadend = deadend
        self._rng = np.random.default_rng(seed)

        self.action_space = spaces.Box(low=-2.0, high=2.0, shape=(1,), dtype=np.float32)
        self.observation_space = spaces.Box(
            low=-np.inf, high=np.inf, shape=(window + 1,), dtype=np.float32
        )

        self._reset_state()

    def _reset_state(self):
        self._series = self.closes
        self._cursor = self.window
        self._end = len(self.closes) - 1
        self.position = 0.0
        self._mean = 0.0
        self._std = 1.0

    # -- gymnasium API -----------------------------------------------------
    def reset(self, *, seed: Optional[int] = None, options=None):
        if seed is not None:
            self._rng = np.random.default_rng(seed)

        span = self.episode_length or (len(self.closes) - self.window - 1)
        span = min(span, len(self.closes) - self.window - 1)
        max_start = len(self.closes) - self.window - span - 1
        start = int(self._rng.integers(0, max_start + 1)) if max_start > 0 else 0

        self._series = self.closes[start : start + self.window + span + 1]
        self._cursor = self.window
        self._end = len(self._series) - 1

        obs = self._observe(initialize_position=True)
        return obs, {}

    def step(self, action):
        self.position += float(action[0]) * self._std
        target = self._series[self._cursor]
        error = abs(target - self.position) / self._std

        if self.deadend:
            if error < 1.0:
                reward = 1.0 - error
                terminated = False
            else:
                reward = -1.0
                terminated = True
        else:
            reward = -error
            terminated = False

        self._cursor += 1
        truncated = self._cursor >= self._end
        obs = self._observe(initialize_position=False)
        return obs, float(reward), bool(terminated), bool(truncated), {}

    # -- internals ---------------------------------------------------------
    def _window_slice(self) -> np.ndarray:
        return self._series[self._cursor - self.window : self._cursor]

    def _observe(self, initialize_position: bool) -> np.ndarray:
        win = self._window_slice()
        self._mean = float(win.mean())
        self._std = float(win.std()) + 1e-4
        if initialize_position:
            self.position = float(win[-1])
        normalized = (win - self._mean) / self._std
        pos_norm = (self.position - self._mean) / self._std
        return np.concatenate([normalized, [pos_norm]]).astype(np.float32)

    # -- constructors ------------------------------------------------------
    @classmethod
    def from_candle(cls, candle, **kwargs) -> "ChartFollowingEnv":
        """Build an env from a :class:`~yammyquant.data.candle.Candle`."""
        return cls(candle.close, **kwargs)
