# Get gym env from gym_env.py
import os

import matplotlib.pyplot as plt
import numpy as np

from pushworld.config import BENCHMARK_PUZZLES_PATH
from pushworld.gym_env import PushWorldEnv

print(f"BENCHMARK_PUZZLES_PATH: {BENCHMARK_PUZZLES_PATH}")

# Create env
env = PushWorldEnv(
    puzzle_path=os.path.join(
        BENCHMARK_PUZZLES_PATH, "level0_transformed", "base", "train"
    )
)


# Set up matplotlib for interactive plotting
plt.ion()
fig, ax = plt.subplots(figsize=(5, 5))

# Reset environment and render initial state
obs, info = env.reset()
img = ax.imshow(obs)
plt.draw()
plt.pause(0.1)
NUM_ACTIONS = env.action_space.n

# Main render loop with random actions
try:
    while True:
        # Take random action
        action = np.random.randint(
            NUM_ACTIONS
        )  # Random action (0-3 for Up, Down, Left, Right)
        obs, reward, done, truncated, info = env.step(action)

        # Update display
        img.set_data(obs)
        plt.draw()
        plt.pause(0.5)  # Pause to make actions visible

        # Optional: reset if puzzle is solved or truncated
        if done or truncated:
            print("Episode finished! Resetting...")
            obs, info = env.reset()

except KeyboardInterrupt:
    print("\nStopping render loop...")
    plt.close()
