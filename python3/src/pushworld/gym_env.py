# Copyright 2022 DeepMind Technologies Limited
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import random
from typing import Optional, Tuple, Union

import gymnasium as gym
import numpy as np
import pygame

from pushworld.config import PUZZLE_EXTENSION
from pushworld.puzzle import (
    DEFAULT_BORDER_WIDTH,
    DEFAULT_PIXELS_PER_CELL,
    NUM_ACTIONS,
    BraindeadPushWorldPuzzle,
    PushWorldPuzzle,
)
from pushworld.utils.env_utils import (
    get_max_puzzle_dimensions,
    render_observation_padded,
)
from pushworld.utils.filesystem import iter_files_with_extension


class PushWorldEnv(gym.Env):
    """
    A Gymnasium environment for PushWorld puzzles.

    Rewards are calculated according to Appendix D of
    https://arxiv.org/pdf/1707.06203.pdf with one change: The negative reward per step
    is reduced to 0.01, since PushWorld puzzles tend to have longer solutions than
    Sokoban puzzles.

    Args:
        puzzle_path: The path of a PushWorld puzzle file or of a directory that
            contains puzzle files, possibly nested in subdirectories. All discovered
            puzzles are loaded, and the `reset` method randomly selects a new puzzle
            each time it is called.
        max_steps: If not None, the `step` method will return `done = True` after
            calling it `max_steps` times since the most recent call of `reset`.
        border_width: The pixel width of the border drawn to indicate object boundaries.
            Must be >= 1.
        pixels_per_cell: The pixel width and height of a discrete position in the environment.
            Must be >= 1 + 2 * border_width.
        standard_padding: If True, all puzzles are padded to the maximum width and
            height of the puzzles in the `pushworld.config.BENCHMARK_PUZZLES_PATH`
            directory. If False, puzzles are padded to the maximum dimensions of
            all puzzles found in the `puzzle_path`.
        render_mode: The mode to use when rendering. Gymnasium expects this to be set on the
            environment. (Currently only "rgb_array" is supported.)
    """

    # For Gymnasium, metadata is usually defined as a class attribute.
    metadata = {"render_modes": ["rgb_array", "human"], "render_fps": 30}

    def __init__(
        self,
        puzzle_path: str,
        braindead: bool = False,
        seed: Optional[int] = 123,
        max_steps: Optional[int] = None,
        border_width: int = DEFAULT_BORDER_WIDTH,
        pixels_per_cell: int = DEFAULT_PIXELS_PER_CELL,
        standard_padding: bool = False,
        render_mode: Optional[str] = None,
    ) -> None:
        # Call the parent constructor (Gymnasium recommends this)
        super().__init__()

        # Store render_mode
        self.render_mode = render_mode
        self.braindead = braindead

        # Initialize pygame display if using human render mode
        self.window = None
        self.clock = None
        self.window_size = None
        if self.render_mode == "human":
            pygame.init()
            pygame.display.init()
            self.clock = pygame.time.Clock()

        self._puzzles = []
        for puzzle_file_path in iter_files_with_extension(
            puzzle_path, PUZZLE_EXTENSION
        ):
            self._puzzles.append(
                BraindeadPushWorldPuzzle(puzzle_file_path)
                if self.braindead
                else PushWorldPuzzle(puzzle_file_path)
            )

        if len(self._puzzles) == 0:
            raise ValueError(f"No PushWorld puzzles found in: {puzzle_path}")
        if border_width < 1:
            raise ValueError("border_width must be >= 1")
        if pixels_per_cell < 3:
            raise ValueError("pixels_per_cell must be >= 3")

        self._max_steps = max_steps
        self._pixels_per_cell = pixels_per_cell
        self._border_width = border_width

        widths, heights = zip(*[puzzle.dimensions for puzzle in self._puzzles])
        self._max_cell_width = max(widths)
        self._max_cell_height = max(heights)

        if standard_padding:
            standard_cell_height, standard_cell_width = get_max_puzzle_dimensions()
            if standard_cell_height < self._max_cell_height:
                raise ValueError(
                    "`standard_padding` is True, but the maximum puzzle height in "
                    "BENCHMARK_PUZZLES_PATH is less than the height of the puzzle(s) "
                    "in the given `puzzle_path`."
                )
            else:
                self._max_cell_height = standard_cell_height
            if standard_cell_width < self._max_cell_width:
                raise ValueError(
                    "`standard_padding` is True, but the maximum puzzle width in "
                    "BENCHMARK_PUZZLES_PATH is less than the width of the puzzle(s) "
                    "in the given `puzzle_path`."
                )
            else:
                self._max_cell_width = standard_cell_width

        # Use a fixed arbitrary seed for reproducibility of results and for
        # deterministic tests.
        self._random_generator = random.Random(seed)

        self._current_puzzle = None
        self._current_state = None

        # Define the action space and observation space as attributes.
        self._action_space = gym.spaces.Discrete(NUM_ACTIONS)
        example_obs = (
            self._puzzles[0].render(self._puzzles[0].initial_state)
            if self.braindead
            else render_observation_padded(
                self._puzzles[0],
                self._puzzles[0].initial_state,
                self._max_cell_height,
                self._max_cell_width,
                self._pixels_per_cell,
                self._border_width,
            )
        )
        self._observation_space = gym.spaces.Box(
            low=0.0,
            high=1.0,
            shape=example_obs.shape,
            dtype=np.float32,
        )

    @property
    def action_space(self) -> gym.spaces.Space:
        """Implements `gym.Env.action_space`."""
        return self._action_space

    @property
    def observation_space(self) -> gym.spaces.Space:
        """Implements `gym.Env.observation_space`."""
        return self._observation_space

    @property
    def current_puzzle(self) -> PushWorldPuzzle or None:
        """The current puzzle, or `None` if `reset` has not yet been called."""
        return self._current_puzzle

    def reset(
        self,
        seed: Optional[int] = None,
        options: Optional[dict] = None,
    ) -> Tuple[np.ndarray, dict]:
        """Implements `gym.Env.reset`.

        This function randomly selects a puzzle from those provided to the constructor
        and resets the environment to the initial state of the puzzle.

        Args:
            seed: If not None, the random number generator in this environment is reset
                with this seed.
            options: Unused. Required by the `gym.Env.reset` interface.

        Returns:
            A tuple of (observation, info). The observation contains the initial
            observation of the environment after the reset, and it is formatted as an
            RGB image with shape (height, width, 3) with `float32` type and values
            ranging from [0, 1]. The info dictionary is unused.
        """
        if options is None or options["maintain_puzzle"] is False:
            if seed is not None:
                self._random_generator = random.Random(seed)

            self._current_puzzle = self._random_generator.choice(self._puzzles)
        else:
            # If we do want to maintain puzzle,
            pass

        self._current_state = self._current_puzzle.initial_state
        self._current_achieved_goals = self._current_puzzle.count_achieved_goals(
            self._current_state
        )
        self._steps = 0
        # observation = render_observation_padded(
        #     self._current_puzzle,
        #     self._current_state,
        #     self._max_cell_height,
        #     self._max_cell_width,
        #     self._pixels_per_cell,
        #     self._border_width,
        # )

        if self.braindead:
            observation = self._current_puzzle.render(self._current_state)
        else:
            observation = self._current_puzzle.render_simple(self._current_state)
        info = {"puzzle_state": self._current_state}

        return observation, info

    def step(
        self, action: int
    ) -> Union[
        Tuple[np.ndarray, float, bool, dict], Tuple[np.ndarray, float, bool, bool, dict]
    ]:
        """Implements `gym.Env.step`.

        The returned observation is an RGB image of the new state of the environment,
        formatted as a `float32` array with shape (height, width, 3) and values ranging
        from [0, 1].
        """
        if not self._action_space.contains(action):
            raise ValueError(
                "The provided action is not in the action space. Provided action: "
                + str(action)
            )

        if self._current_state is None:
            raise RuntimeError("reset() must be called before step() can be called.")

        self._steps += 1
        previous_state = self._current_state
        self._current_state = self._current_puzzle.get_next_state(
            self._current_state, action
        )
        # observation = render_observation_padded(
        #     self._current_puzzle,
        #     self._current_state,
        #     self._max_cell_height,
        #     self._max_cell_width,
        #     self._pixels_per_cell,
        #     self._border_width,
        # )
        if self.braindead:
            observation = self._current_puzzle.render(self._current_state)
        else:
            observation = self._current_puzzle.render_simple(self._current_state)

        terminated = self._current_puzzle.is_goal_state(self._current_state)

        if terminated:
            reward = 10.0
        else:
            previous_achieved_goals = self._current_puzzle.count_achieved_goals(
                previous_state
            )
            current_achieved_goals = self._current_puzzle.count_achieved_goals(
                self._current_state
            )
            reward = current_achieved_goals - previous_achieved_goals - 0.01

        truncated = False if self._max_steps is None else self._steps >= self._max_steps
        info = {"puzzle_state": self._current_state}

        if self.render_mode == "human":
            self.render()

        return observation, reward, terminated, truncated, info

    def render(self) -> Optional[np.ndarray]:
        """Renders the current puzzle state as an RGB array or to a window."""

        # Get the RGB array representation of the current state
        rgb_array = self._current_puzzle.render(
            self._current_state,
            border_width=self._border_width,
            pixels_per_cell=self._pixels_per_cell,
        )

        if self.render_mode == "human":
            # Initialize window if it doesn't exist
            if self.window is None:
                pygame.display.set_caption("PushWorld")
                self.window_size = rgb_array.shape[:2]
                self.window = pygame.display.set_mode(
                    (self.window_size[1], self.window_size[0])
                )

            # Convert numpy array to pygame surface
            surf = pygame.surfarray.make_surface(rgb_array)

            # Display the surface
            self.window.blit(surf, (0, 0))
            pygame.event.pump()
            pygame.display.update()

            # Ensure consistent framerate
            if self.clock is not None:
                self.clock.tick(self.metadata["render_fps"])

            return None

        elif self.render_mode == "rgb_array":
            return rgb_array

        else:
            raise ValueError(f"Unsupported render mode: {self.render_mode}")

    def close(self):
        """Clean up resources when environment is no longer needed."""
        if self.window is not None:
            pygame.display.quit()
            pygame.quit()
            self.window = None
