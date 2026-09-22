"""Synthetic contested-terrain worlds for the closed-loop navigation demo.

A world is a square arena with axis-aligned rectangular obstacles. Everything is
batched: the leading axis is the episode, so K worlds are carried in one array
and every operation below is a whole-array numpy operation.

Boxes are stored as (x_min, y_min, x_max, y_max) in metres, world frame.
"""

import numpy as np

SIZE = 20.0            # arena side, metres
RES = 0.5              # occupancy grid resolution, metres
NCELL = int(round(SIZE / RES))
START_RC = (2, 2)      # grid (row, col) of the start cell
GOAL_RC = (37, 37)     # grid (row, col) of the goal cell

MAX_OBSTACLES = 9
MIN_OBSTACLES = 5
HALF_EXTENT = (0.6, 1.6)   # per-axis half extent, metres, uniform
MARGIN = 3.0               # obstacle centres stay this far from the arena edge
CLEARANCE = 1.0            # obstacles this close to start or goal are dropped
P_HARD = 0.15              # fraction of objects the detector underestimates badly
ROBOT_HALF = 0.35          # half side of the square robot footprint, metres


def cell_centres():
    """x coordinates of the NCELL grid columns (same values for the rows)."""
    return (np.arange(NCELL) + 0.5) * RES


def cell_xy(rc):
    """World (x, y) of a grid (row, col)."""
    r, c = rc
    return np.array([(c + 0.5) * RES, (r + 0.5) * RES])


START_XY = cell_xy(START_RC)
GOAL_XY = cell_xy(GOAL_RC)


def sample_worlds(rng, n):
    """Draw n worlds. Returns boxes (n, M, 4), valid (n, M), hard (n, M).

    Boxes whose slot is not valid are ignored everywhere downstream; the count
    of real obstacles per world is uniform on [MIN_OBSTACLES, MAX_OBSTACLES].
    Obstacles that would sit on the start or the goal are dropped.
    """
    m = MAX_OBSTACLES
    centre = rng.uniform(MARGIN, SIZE - MARGIN, size=(n, m, 2))
    half = rng.uniform(HALF_EXTENT[0], HALF_EXTENT[1], size=(n, m, 2))
    boxes = np.concatenate([centre - half, centre + half], axis=2)

    count = rng.integers(MIN_OBSTACLES, MAX_OBSTACLES + 1, size=(n, 1))
    valid = np.arange(m)[None, :] < count

    for anchor in (START_XY, GOAL_XY):
        inside = np.all(
            (boxes[:, :, :2] - CLEARANCE <= anchor) & (anchor <= boxes[:, :, 2:] + CLEARANCE),
            axis=2,
        )
        valid = valid & ~inside

    hard = rng.random((n, m)) < P_HARD
    return boxes, valid, hard


def inside_any(boxes, valid, pts):
    """True where a point lies in some valid box.

    boxes (K, M, 4), valid (K, M), pts (K, P, 2) -> (K, P).
    """
    lo = boxes[:, :, None, :2]
    hi = boxes[:, :, None, 2:]
    hit = np.all((lo <= pts[:, None, :, :]) & (pts[:, None, :, :] <= hi), axis=3)
    return np.any(hit & valid[:, :, None], axis=1)
