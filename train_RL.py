import gymnasium as gym
from gym_env import ChartFollowing

from stable_baselines3 import SAC

env = ChartFollowing()

# model = SAC("MlpPolicy", env, verbose=1)
# for i in range(5):
#     model.learn(total_timesteps=10000, log_interval=4, progress_bar=True)
#     model.save("ChartFollowing_SAC")

# del model # remove to demonstrate saving and loading

model = SAC.load("ChartFollowing_SAC")

obs = env.reset()
while True:
    action, _states = model.predict(obs, deterministic=True)
    
    obs, reward, terminated, info = env.step(action)
    env.render()
    if terminated or terminated:
        obs = env.reset()