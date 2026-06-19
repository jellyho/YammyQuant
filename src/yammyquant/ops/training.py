"""RL training pipeline — ``yq train``.

Builds a :class:`ChartFollowingEnv` from stored candles and trains a
Stable-Baselines3 agent on it, recording progress to the cockpit. The env
construction is dependency-light and unit-tested; the actual training imports
``stable_baselines3`` lazily so the rest of the platform doesn't require it.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from yammyquant.data.sources.store import DuckDBStore
from yammyquant.state.store import LiveState


def build_env(
    store: DuckDBStore,
    ticker: str,
    interval: str,
    window: int = 10,
    episode_length: Optional[int] = 200,
    deadend: bool = True,
):
    """Construct a ChartFollowingEnv from stored candles (testable, no SB3)."""
    from yammyquant.rl.env import ChartFollowingEnv

    candle = store.read(ticker, interval)
    return ChartFollowingEnv.from_candle(
        candle, window=window, episode_length=episode_length, deadend=deadend
    )


def train(
    store: DuckDBStore,
    ticker: str,
    interval: str,
    timesteps: int = 10_000,
    window: int = 10,
    episode_length: Optional[int] = 200,
    deadend: bool = True,
    algo: str = "SAC",
    models_dir: str | Path = "models",
    state: Optional[LiveState] = None,
) -> dict:
    """Train an SB3 agent on the chart-following env and save a checkpoint."""
    from stable_baselines3 import SAC, PPO  # optional [rl] dependency

    env = build_env(store, ticker, interval, window, episode_length, deadend)
    Model = {"SAC": SAC, "PPO": PPO}.get(algo.upper())
    if Model is None:
        raise ValueError(f"unsupported algo {algo!r}; choose SAC or PPO")

    if state:
        state.log("train", f"training {algo} on {ticker}/{interval} for {timesteps} steps",
                  window=window, deadend=deadend)

    model = Model("MlpPolicy", env, verbose=0)
    model.learn(total_timesteps=timesteps)

    out = Path(models_dir)
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"{algo.lower()}_{ticker}_{interval}"
    model.save(str(path))

    result = {"algo": algo, "ticker": ticker, "interval": interval,
              "timesteps": timesteps, "checkpoint": f"{path}.zip"}
    if state:
        state.log("train", f"saved checkpoint {path}.zip", **result)
    return result
