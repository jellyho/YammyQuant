"""RL example: train SAC on the ChartFollowing env (gymnasium API).

Requires the optional rl extra:
    pip install 'yammyquant[rl]'
    python examples/train_rl.py
"""

import numpy as np

from yammyquant.rl.env import ChartFollowingEnv


def synthetic_closes(n: int = 5000) -> np.ndarray:
    t = np.arange(n)
    rng = np.random.default_rng(0)
    return 100 + 10 * np.sin(t / 50.0) + np.cumsum(rng.normal(0, 0.2, n))


def main():
    from stable_baselines3 import SAC

    env = ChartFollowingEnv(synthetic_closes(), window=10, episode_length=200, deadend=True)
    model = SAC("MlpPolicy", env, verbose=1)
    model.learn(total_timesteps=10_000, progress_bar=True)
    model.save("chart_following_sac")
    print("saved -> chart_following_sac.zip")


if __name__ == "__main__":
    main()
