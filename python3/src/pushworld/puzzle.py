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

from collections import defaultdict
from dataclasses import dataclass
from typing import Iterable, List, Set, Tuple

import numpy as np

# The default pixel width of the border drawn to indicate object boundaries.
DEFAULT_BORDER_WIDTH = 2

# The default pixel width and height of a discrete position (i.e. cell) in a
# PushWorld environment.
DEFAULT_PIXELS_PER_CELL = 20

NUM_ACTIONS = 4
AGENT_IDX = 0


class Actions:
    """An enumeration of available actions in the PushWorld environment."""

    LEFT, RIGHT, UP, DOWN = range(NUM_ACTIONS)

    FROM_CHAR = {
        "L": LEFT,
        "R": RIGHT,
        "U": UP,
        "D": DOWN,
    }
    DISPLACEMENTS = np.array(
        [
            (-1, 0),  # LEFT
            (1, 0),  # RIGHT
            (0, -1),  # UP
            (0, 1),  # DOWN
        ]
    )


# Type aliases
Point = Tuple[int, int]
State = Tuple[Point, ...]
Color = Tuple[int, int, int]  # (red, green, blue) with range 0 - 255


def hex_to_rgb(hex_string: str) -> Color:
    """Converts a standard 6-digit hex color into a tuple of decimal
    (red, green, blue) values."""
    return tuple(int(hex_string[i : i + 2], 16) for i in (0, 2, 4))


class Colors:
    """An enumeration of all colors involved in rendering a PushWorld puzzle."""

    AGENT = hex_to_rgb("00DC00")
    AGENT_BORDER = hex_to_rgb("006E00")
    AGENT_WALL = hex_to_rgb("FAC71E")
    AGENT_WALL_BORDER = hex_to_rgb("7D640F")
    GOAL = None  # transparent
    GOAL_BORDER = hex_to_rgb("B90000")
    GOAL_OBJECT = hex_to_rgb("DC0000")
    GOAL_OBJECT_BORDER = hex_to_rgb("6E0000")
    MOVABLE = hex_to_rgb("469BFF")
    MOVABLE_BORDER = hex_to_rgb("23487F")
    WALL = hex_to_rgb("0A0A0A")
    WALL_BORDER = hex_to_rgb("050505")


@dataclass(frozen=True)
class PushWorldObject:
    """An object in the the PushWorld environment.

    Attributes:
        position: The absolute position of the object.
        fill_color: The color with which to fill the object's area when rendered.
        border_color: The color of the object's border when rendered.
        cells: The discrete positions that this object occupies, defined relative to
            the object's frame.
    """

    position: Point
    fill_color: Color
    border_color: Color
    cells: Set[Point]


class PushWorldPuzzle:
    """A puzzle in the PushWorld environment.

    Args:
        file_path: The path to a `.pwp` file that defines the puzzle.

    Attributes:
        initial_state: The initial state from which a plan must be found to achieve the
            goal.
        goal_state: Defines the goal to achieve from the initial state.
        dimensions: A (width, height) tuple of the number of discrete positions in
            the puzzle.
        wall_positions: The discrete positions of all walls.
        agent_wall_positions: The discrete positions of all walls that only block the
            movement of the agent object.
        movable_objects: A list of all movable objects, including their shapes.

    Methods:
        get_next_state: Returns the state that results from performing an action from a
            given state.
        count_achieved_goals: Returns the number of objects that are in their goal
            positions in a given state.
        is_goal_state: Returns whether the given state satisfies the goal of this
            puzzle.
        is_valid_plan: Returns whether the sequence of actions in the plan achieves the
            goal, starting from the initial state.
        render: Creates an image of a given state.
        render_plan: Creates a video of a given plan, starting from the initial state.
    """

    def __init__(self, file_path: str) -> None:
        obj_pixels = defaultdict(set)

        self._name = file_path.split("/")[-1].split(".")[0]

        with open(file_path, "r") as fi:
            elems_per_row = -1
            for line_idx, line in enumerate(fi):
                y = line_idx + 1
                line_elems = line.split()
                if y == 1:
                    elems_per_row = len(line_elems)
                else:
                    if elems_per_row != len(line_elems):
                        raise ValueError(
                            f"Row {y} does not have the same number of elements as "
                            "the first row."
                        )

                for x in range(1, len(line_elems) + 1):
                    cell_elems = line_elems[x - 1].split("+")
                    for elem_id in cell_elems:
                        elem_id = elem_id.lower()
                        if elem_id != ".":
                            obj_pixels[elem_id].add((x, y))

        if "a" not in obj_pixels:
            raise ValueError(
                "Every puzzle must have an agent object, indicated by 'a'."
            )

        # Add walls at the boundaries of the puzzle
        width = self._width = x + 2
        height = self._height = y + 2

        for xx in range(width):
            obj_pixels["w"].add((xx, 0))
            obj_pixels["w"].add((xx, height - 1))
        for yy in range(height):
            obj_pixels["w"].add((0, yy))
            obj_pixels["w"].add((width - 1, yy))

        movables = ["a"]
        self._goal_state = ()
        object_positions = {}
        self._movable_objects = []
        self._goals = []
        self._agent_walls = None

        # Put the agent in front of all other movables
        sorted_elem_ids = list(obj_pixels.keys())
        sorted_elem_ids.sort(reverse=True)

        for elem_id in sorted_elem_ids:
            pixels = obj_pixels[elem_id]

            if elem_id == "w" or elem_id == "aw":
                position = (0, 0)
            else:
                xx, yy = zip(*pixels)
                # We are getting the coordinates to use as the object's frame of reference
                position = (min(xx), min(yy))

            pixels = subtract_from_points(pixels, position)
            # Here, obj_pixels stores coordinates of objects relative to the position variable above
            # object_positions simply stores the object's frame of reference coordinates
            # In this case, pixels is more like "actual frame"
            object_positions[elem_id] = position
            obj_pixels[elem_id] = pixels

            if elem_id == "w":
                self._walls = PushWorldObject(
                    position=position,
                    fill_color=Colors.WALL,
                    border_color=Colors.WALL_BORDER,
                    cells=pixels,
                )
            elif elem_id == "aw":
                self._agent_walls = PushWorldObject(
                    position=position,
                    fill_color=Colors.AGENT_WALL,
                    border_color=Colors.AGENT_WALL_BORDER,
                    cells=pixels,
                )
            elif elem_id == "a":
                self._movable_objects.append(
                    PushWorldObject(
                        position=position,
                        fill_color=Colors.AGENT,
                        border_color=Colors.AGENT_BORDER,
                        cells=pixels,
                    )
                )
            elif elem_id[0] == "g":
                self._goals.append(
                    PushWorldObject(
                        position=position,
                        fill_color=Colors.GOAL,
                        border_color=Colors.GOAL_BORDER,
                        cells=pixels,
                    )
                )

            if elem_id[0] == "g":
                self._goal_state += (object_positions[elem_id],)
                movable_id = "m" + elem_id[1:]
                assert (
                    movable_id in obj_pixels
                ), f"Goal has no associated movable object: {movable_id}"
                movables.append(movable_id)

        for elem_id in obj_pixels:
            if elem_id[0] == "m" and elem_id not in movables:
                movables.append(elem_id)

        for i, elem_id in enumerate(movables[1:]):
            self._movable_objects.append(
                PushWorldObject(
                    position=object_positions[elem_id],
                    fill_color=Colors.MOVABLE
                    if i >= len(self._goal_state)
                    else Colors.GOAL_OBJECT,
                    border_color=Colors.MOVABLE_BORDER
                    if i >= len(self._goal_state)
                    else Colors.GOAL_OBJECT_BORDER,
                    cells=obj_pixels[elem_id],
                )
            )

        self._agent_wall_positions = obj_pixels["aw"]
        self._wall_positions = obj_pixels["w"]

        # Goal state is the coordinate of the goal object
        self._goal_state = tuple(self._goal_state)
        # Initial state is the coordinate of the movable objects (including agents and boxes)
        self._initial_state = tuple(object_positions[elem_id] for elem_id in movables)

        # Create all collision data structures

        num_movables = self.num_movables = len(movables)
        self._agent_collision_map = [set() for i in range(NUM_ACTIONS)]
        self._wall_collision_map = [
            [set() for i in range(num_movables)] for a in range(NUM_ACTIONS)
        ]
        self._movable_collision_map = [
            [[set() for i in range(num_movables)] for j in range(num_movables)]
            for a in range(NUM_ACTIONS)
        ]

        # Populate the actor collisions
        for a in range(NUM_ACTIONS):
            obj_pixels["aw"].update(obj_pixels["w"])
            _populate_static_collisions(
                collision_positions=self._agent_collision_map[a],
                action=a,
                object_pixels=obj_pixels["a"],
                static_obstacle_pixels=obj_pixels["aw"],
                width=width,
                height=height,
            )

        # Populate the wall collisions of all movables other than the agent
        for m in range(1, num_movables):
            for a in range(NUM_ACTIONS):
                _populate_static_collisions(
                    collision_positions=self._wall_collision_map[a][m],
                    action=a,
                    object_pixels=obj_pixels[movables[m]],
                    static_obstacle_pixels=obj_pixels["w"],
                    width=width,
                    height=height,
                )

        # Populate the collisions between all movables. There is no need to store
        # collisions caused by movables pushing the agent, since the agent is the
        # cause of all movement.
        for pusher in range(num_movables):
            for pushee in range(1, num_movables):
                for a in range(NUM_ACTIONS):
                    _populate_dynamic_collisions(
                        collision_positions=(
                            self._movable_collision_map[a][pusher][pushee]
                        ),
                        action=a,
                        pusher_pixels=obj_pixels[movables[pusher]],
                        pushee_pixels=obj_pixels[movables[pushee]],
                    )

        self._pushed_objects = np.zeros((num_movables,), bool)
        self._pushed_objects[AGENT_IDX] = True

    @property
    def name(self) -> str:
        return self._name

    @property
    def initial_state(self) -> State:
        """The initial state from which a plan must be found to achieve the goal."""
        return self._initial_state

    @property
    def goal_state(self) -> Tuple[Point]:
        """Defines the goal to achieve from the initial state.

        The kth element in the goal state defines the goal position of the (k+1)th
        element in each `State`.
        """
        return self._goal_state

    @property
    def dimensions(self) -> Tuple[int, int]:
        """A (width, height) tuple of the number of discrete positions in the puzzle."""
        return (self._width, self._height)

    @property
    def wall_positions(self) -> Set[Point]:
        """The discrete positions of all walls."""
        return self._wall_positions

    @property
    def agent_wall_positions(self) -> Set[Point]:
        """The discrete positions of all walls that only block the movement of the
        agent object."""
        return self._agent_wall_positions

    @property
    def movable_objects(self) -> List[PushWorldObject]:
        """A list of all movable objects, including their shapes."""
        return self._movable_objects

    def get_next_state(self, state: State, action: int) -> State:
        """Returns the state that results from performing the `action` in the given
        `state`."""
        agent_pos = state[AGENT_IDX]

        if agent_pos in self._agent_collision_map[action]:
            return state  # the actor cannot move

        walls = self._wall_collision_map[action]
        frontier = [AGENT_IDX]

        while frontier:
            movable_idx = frontier.pop()
            movable_pos = state[movable_idx]
            movable_collisions = self._movable_collision_map[action][movable_idx]

            for obstacle_idx in range(1, self.num_movables):
                if self._pushed_objects[obstacle_idx]:
                    continue  # already pushed

                # Is obstacle_idx pushed by movable_idx?
                obstacle_pos = state[obstacle_idx]
                relative_pos = tuple(np.subtract(movable_pos, obstacle_pos))

                if relative_pos not in movable_collisions[obstacle_idx]:
                    continue  # obstacle_idx is not pushed by movable_idx

                # obstacle_idx is being pushed by movable_idx
                if obstacle_pos in walls[obstacle_idx]:
                    # transitive stopping; nothing can move.
                    self._pushed_objects[1:] = False
                    return state

                self._pushed_objects[obstacle_idx] = True
                frontier.append(obstacle_idx)

        next_state = list(state)
        displacement = Actions.DISPLACEMENTS[action]
        next_state[0] = tuple(displacement + state[0])
        for i in range(1, self.num_movables):
            if self._pushed_objects[i]:
                next_state[i] = tuple(displacement + state[i])
                self._pushed_objects[i] = False
            else:
                next_state[i] = state[i]

        return tuple(next_state)

    def count_achieved_goals(self, state: State) -> int:
        """Returns the number of objects that are in their goal positions in a
        given state."""
        count = 0

        for entity, goal_entity in zip(
            state[1 : 1 + len(self._goal_state)], self._goal_state
        ):
            if entity == goal_entity:
                count += 1

        return count

    def is_goal_state(self, state: State) -> bool:
        """Returns whether the given state satisfies the goal of this puzzle."""
        return state[1 : 1 + len(self._goal_state)] == self._goal_state

    def is_valid_plan(self, plan: Iterable[int]) -> bool:
        """Returns whether the sequence of actions in the plan achieves the goal,
        starting from the initial state."""
        state = self._initial_state

        for action in plan:
            if self.is_goal_state(state):
                # goal was achieved before the plan ended
                return False
            state = self.get_next_state(state, action)

        return self.is_goal_state(state)

    def render(
        self,
        state: State,
        border_width: int = DEFAULT_BORDER_WIDTH,
        pixels_per_cell: int = DEFAULT_PIXELS_PER_CELL,
    ) -> np.ndarray:
        """Creates an image of the given state.

        Args:
            state: The state to render.
            border_width: The pixel width of the border drawn to indicate object
                boundaries. Must be >= 1.
            pixels_per_cell: The pixel width and height of a discrete position in the
                environment. Must be >= 1 + 2 * border_width.

        Returns:
            An RGB image with shape (height, width, 3) and type `uint8`.
        """
        if border_width < 1:
            raise ValueError("border_width must be >= 1")

        if pixels_per_cell < 1 + 2 * border_width:
            raise ValueError("pixels_per_cell must be >= 1 + 2*border_width")

        image_shape = (self._height * pixels_per_cell, self._width * pixels_per_cell, 3)
        image = np.ones(image_shape, np.uint8) * 255

        objects = [(self._walls, self._walls.position)]
        if self._agent_walls is not None:
            objects.insert(0, (self._agent_walls, self._agent_walls.position))

        objects += zip(self._movable_objects, state)
        objects += [(g, g.position) for g in self._goals]

        for obj, pos in objects:
            _draw_object(
                obj=obj,
                position=pos,
                image=image,
                pixels_per_cell=pixels_per_cell,
                border_width=border_width,
            )

        return image

    def render_simple(
        self,
        state: State,
    ) -> np.ndarray:
        """Creates a simplified representation of the given state. We return a 2D array where each element encodes
        the identity of the object in the corresponding position.

        Agent: 1
        Movable : 2
        Wall: 3
        Goal: 4

        Args:
            state: The state to render.
            border_width: The pixel width of the border drawn to indicate object
                boundaries. Must be >= 1.
            pixels_per_cell: The pixel width and height of a discrete position in the
                environment. Must be >= 1 + 2 * border_width.

        Returns:
            The 2D array of shape (height, width) with integer values.
        """

        # 2D np array of size self._height and self._width
        image = np.zeros((self._height, self._width), np.uint8)

        # Loop through self._walls and populate the image with 3s
        for wall_coord in self._walls.cells:
            image[wall_coord] = 3

        # First movable object is the agent
        image[state[0]] = 1

        # Loop through self._movable_objects and populate the image with 2s
        for movable_coord in state[1:]:
            image[movable_coord] = 2

        # Loop through self._goals and populate the image with 4s
        for goal_coord in self._goal_state:
            image[goal_coord] = 4

        # Create empty tensor [4, height, width]
        one_hot = np.zeros((4, self._height, self._width), dtype=np.float32)
        # Fill in the one-hot channels
        for i in range(1, 5):  # For each object type (0-3)
            one_hot[i - 1] = (image == i).astype(np.float32)

        # Reshape to height, width, channel (H x W x C)
        one_hot = one_hot.transpose(1, 2, 0)

        return one_hot

    def render_plan(
        self,
        plan: Iterable[int],
        border_width: int = DEFAULT_BORDER_WIDTH,
        pixels_per_cell: int = DEFAULT_PIXELS_PER_CELL,
    ) -> List[np.ndarray]:
        """Creates a video of the given plan, starting from the initial state.

        Args:
            plan: A sequence of actions.
            border_width: The pixel width of the border drawn to indicate object
                boundaries. Must be >= 1.
            pixels_per_cell: The pixel width and height of a discrete position in the
                environment. Must be >= 1 + 2 * border_width.

        Returns:
            A list of RGB images with shape (height, width, 3) and type `uint8`.
        """
        state = self._initial_state
        image = self.render(
            state=state,
            border_width=border_width,
            pixels_per_cell=pixels_per_cell,
        )
        images = [image]

        for action in plan:
            state = self.get_next_state(state, action)
            image = self.render(
                state=state,
                border_width=border_width,
                pixels_per_cell=pixels_per_cell,
            )
            images.append(image)

        return images


class BraindeadPushWorldPuzzle(PushWorldPuzzle):
    """A simplified puzzle in the PushWorld environment with only an agent and a goal.

    The puzzle is solved when the agent moves into the goal position.
    There are no walls or movable objects other than the agent.

    Args:
        file_path: The path to a `.pwp` file that defines the puzzle.
    """

    def __init__(self, file_path: str) -> None:
        obj_pixels = defaultdict(set)

        # Parse puzzle file
        with open(file_path, "r") as fi:
            elems_per_row = -1
            for line_idx, line in enumerate(fi):
                y = line_idx + 1
                line_elems = line.split()
                if y == 1:
                    elems_per_row = len(line_elems)
                else:
                    if elems_per_row != len(line_elems):
                        raise ValueError(
                            f"Row {y} does not have the same number of elements as "
                            "the first row."
                        )

                for x in range(1, len(line_elems) + 1):
                    elem_id = line_elems[x - 1].lower()
                    if elem_id == "a":  # Agent
                        obj_pixels["a"].add((x, y))
                    elif elem_id.startswith("g"):  # Goal
                        obj_pixels["g1"].add((x, y))

        if "a" not in obj_pixels:
            raise ValueError(
                "Every puzzle must have an agent object, indicated by 'a'."
            )
        if "g1" not in obj_pixels:
            raise ValueError("Every puzzle must have a goal object, indicated by 'g1'.")

        # Set dimensions
        self._width = x  # Last x value from the parse loop
        self._height = y  # Last y value from the parse loop

        # Keep track of agent position
        agent_positions = obj_pixels["a"]
        self._agent_position = next(iter(obj_pixels["a"]))  # Get the only position

        # Keep track of goal position
        goal_positions = obj_pixels["g1"]
        self._goal_position = next(iter(obj_pixels["g1"]))  # Get the only position

        # Store initial state as just the agent position
        self._initial_state = (self._agent_position,)

        # For compatibility with parent class
        self._goal_state = (self._goal_position,)
        self._movable_objects = [
            PushWorldObject(
                position=self._agent_position,
                fill_color=Colors.AGENT,
                border_color=Colors.AGENT_BORDER,
                cells=subtract_from_points(agent_positions, self._agent_position),
            )
        ]
        self._goals = [
            PushWorldObject(
                position=self._goal_position,
                fill_color=Colors.GOAL,
                border_color=Colors.GOAL_BORDER,
                cells=subtract_from_points(goal_positions, self._goal_position),
            )
        ]

        # No walls or agent walls in braindead puzzles
        self._wall_positions = set()
        self._agent_wall_positions = set()

        # For compatibility with parent class
        self.num_movables = 1  # Just the agent
        self._agent_collision_map = [set() for _ in range(NUM_ACTIONS)]
        self._wall_collision_map = [
            [set() for _ in range(self.num_movables)] for _ in range(NUM_ACTIONS)
        ]
        self._movable_collision_map = [
            [
                [set() for _ in range(self.num_movables)]
                for _ in range(self.num_movables)
            ]
            for _ in range(NUM_ACTIONS)
        ]
        self._pushed_objects = np.zeros((self.num_movables,), bool)
        self._pushed_objects[AGENT_IDX] = True

    def get_next_state(self, state: State, action: int) -> State:
        """Returns the state that results from performing the `action` in the given
        `state`.

        In braindead puzzles, only the agent can move, and it can move freely
        without any wall or obstacle constraints.
        """
        agent_pos = state[AGENT_IDX]
        displacement = Actions.DISPLACEMENTS[action]
        new_pos = tuple(np.add(agent_pos, displacement))

        # Check if the new position is within bounds
        if 1 <= new_pos[0] <= self._width and 1 <= new_pos[1] <= self._height:
            return (new_pos,)
        else:
            return state  # Can't move out of bounds

    def is_goal_state(self, state: State) -> bool:
        """Returns whether the given state satisfies the goal of this puzzle.

        In braindead puzzles, the goal is achieved when the agent is at the goal position.
        """
        return state[AGENT_IDX] == self._goal_position

    def count_achieved_goals(self, state: State) -> int:
        """Returns 1 if the goal is achieved, 0 otherwise."""
        return 1 if self.is_goal_state(state) else 0

    def is_valid_plan(self, plan: Iterable[int]) -> bool:
        """Returns whether the sequence of actions in the plan achieves the goal,
        starting from the initial state."""
        state = self._initial_state

        for action in plan:
            if self.is_goal_state(state):
                # goal was achieved before the plan ended
                return True
            state = self.get_next_state(state, action)

        return self.is_goal_state(state)

    def render(
        self,
        state: State,
    ) -> np.ndarray:
        """Creates a simplified representation of the given state.

        Returns:
            A 2-channel 2D array where:
            - Channel 0: Agent position (1 where agent is present)
            - Channel 1: Goal position (1 where goal is present)
        """
        image = np.zeros((self._height, self._width, 2), np.uint8)

        # Populate the 1st channel with agent's position
        agent_pos = state[AGENT_IDX]
        image[agent_pos[1] - 1, agent_pos[0] - 1, 0] = 1

        # Populate the 2nd channel with goal's position
        goal_pos = self._goal_position
        image[goal_pos[1] - 1, goal_pos[0] - 1, 1] = 1

        return image


def points_overlap(s1: Set[Point], s2: Set[Point], offset: Point) -> bool:
    """Returns whether there exists a pair of points (p1, p2) in the sets (s1, s2) such
    that p1 + offset == p2."""
    offset_s2 = subtract_from_points(s2, offset)
    return bool(s1.intersection(offset_s2))


def subtract_from_points(points: Set[Point], offset: Point) -> Set[Point]:
    """Returns the set {p - offset} for all `p` in `points`."""
    dx, dy = offset
    return set((x - dx, y - dy) for x, y in points)


def _populate_static_collisions(
    collision_positions: Set[Point],
    action: int,
    object_pixels: Set[Point],
    static_obstacle_pixels: Set[Point],
    width: int,
    height: int,
) -> None:
    """Computes the positions in which an object moves into collision with a static
    obstacle when moving in the direction of the given `action`.

    Args:
        collision_positions: Modified in place. This function adds all positions of the
            object in which moving the object in the direction of the given `action`
            results in a collision with a static obstacle.
        action: The direction of the movement.
        object_pixels: The pixel positions of the object, measured in the
            object's reference frame.
        static_obstacle_pixels: The pixel positions of static obstacles, measured
            in the global frame.
        width: The maximum x-position of the object.
        height: The maximum y-position of the object.
    """
    dis_x, dis_y = Actions.DISPLACEMENTS[action]

    xx, yy = zip(*object_pixels)
    object_size = (max(xx) - min(xx) + 1, max(yy) - min(yy) + 1)

    width -= object_size[0]
    height -= object_size[1]

    for object_x, object_y in object_pixels:
        for obstacle_x, obstacle_y in static_obstacle_pixels:
            dx = -dis_x + obstacle_x - object_x
            dy = -dis_y + obstacle_y - object_y
            if (
                dx >= 0
                and dy >= 0
                and dx <= width
                and dy <= height
                and not points_overlap(object_pixels, static_obstacle_pixels, (dx, dy))
            ):
                collision_positions.add((dx, dy))


def _populate_dynamic_collisions(
    collision_positions: Set[Point],
    action: int,
    pusher_pixels: Set[Point],
    pushee_pixels: Set[Point],
) -> None:
    """Computes the relative positions between two objects in which one object can
    push the other when it moves in the direction of the given `action`.

    Args:
        collision_positions: Modified in place. This function adds all positions of the
            pusher relative to the pushee in which moving the pusher in the direction
            of the given `action` results in a collision with the pushee.
        action: The direction of the pushing movement.
        pusher_pixels: The pixel positions of the pusher object, measured in the
            object's reference frame.
        pushee_pixels: The pixel positions of the pushee object, measured in the
            object's reference frame.
    """
    dis_x, dis_y = Actions.DISPLACEMENTS[action]

    for pusher_x, pusher_y in pusher_pixels:
        for pushee_x, pushee_y in pushee_pixels:
            dx = -dis_x + pushee_x - pusher_x
            dy = -dis_y + pushee_y - pusher_y
            if not points_overlap(pusher_pixels, pushee_pixels, (dx, dy)):
                collision_positions.add((dx, dy))


def _draw_object(
    obj: PushWorldObject,
    position: Point,
    image: np.ndarray,
    pixels_per_cell: int,
    border_width: int,
) -> None:
    """Draws the object into the given image.

    Args:
        obj: The object to draw.
        position: The (column, row) position of the object.
        image: The image in which to draw the object. Modified in place.
            Must have shape (height, width, 3) and type `uint8`.
        pixels_per_cell: The pixel width and height of a discrete position.
        border_width: The pixel width of the border that highlights object boundaries.
    """
    position = np.array(position)
    border_offsets = [
        (-1, 0),
        (1, 0),
        (0, -1),
        (0, 1),
        (-1, -1),
        (-1, 1),
        (1, -1),
        (1, 1),
    ]

    # Draw the cells and borders
    for cell in obj.cells:
        c, r = (position + cell) * pixels_per_cell
        if obj.fill_color is not None:
            image[r : r + pixels_per_cell, c : c + pixels_per_cell] = obj.fill_color

        for dr, dc in border_offsets:
            if (cell[0] + dc, cell[1] + dr) not in obj.cells:
                # The adjacent cell is empty, so draw a border
                r1 = r + max(0, dr) * (pixels_per_cell - border_width)
                r2 = (r1 + pixels_per_cell) if dr == 0 else (r1 + border_width)
                c1 = c + max(0, dc) * (pixels_per_cell - border_width)
                c2 = (c1 + pixels_per_cell) if dc == 0 else (c1 + border_width)
                image[r1:r2, c1:c2] = obj.border_color
