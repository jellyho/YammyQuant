import gymnasium as gym
from gym_env import ChartFollowingDeploy

from stable_baselines3 import SAC

env = ChartFollowingDeploy()

# model = SAC("MlpPolicy", env, verbose=1)
model = SAC.load("ChartFollowing_SAC")
# model.learn(total_timesteps=100000, log_interval=4, progress_bar=True)
# model.save("ChartFollowing_SAC2")

# del model # remove to demonstrate saving and loading

# model = SAC.load("ChartFollowing_SAC")

obs = env.reset()
while True:
    action, _states = model.predict(obs, deterministic=True)
    
    obs, reward, terminated, info = env.step(action)
    env.render()
    if terminated or terminated:
        obs = env.reset()