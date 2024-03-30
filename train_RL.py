import gymnasium as gym
from gym_env import ChartFollowingDeadend

from stable_baselines3 import SAC

env = ChartFollowingDeadend()

model = SAC("MlpPolicy", env, verbose=1)
# model.load("ChartFollowingDeadend_SAC")
model.learn(total_timesteps=10000, log_interval=100, progress_bar=True)
model.save("ChartFollowingDeadend_SAC")

del model # remove to demonstrate saving and loading

model = SAC.load("ChartFollowingDeadend_SAC")

obs = env.reset()
while True:
    action, _states = model.predict(obs, deterministic=True)
    
    obs, reward, terminated, info = env.step(action)
    env.render()
    if terminated or terminated:
        obs = env.reset()