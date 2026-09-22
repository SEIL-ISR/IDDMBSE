"""An analytic model of the Isaac Sim test range, for the model-based stage.

The range is itself a design under trade: a test range has to be contested
enough to tell robot designs apart and traversable enough that a run produces
data. `isaacsim/tools/range_doe.py` turns five knobs into a USD layer -- the
obstacle coverage, the 99th-percentile slope target, a static/dynamic friction
pair and a restitution -- and this module predicts, from the same knobs and the
same heightmap, what a trial on that layer will face before any trial runs.

Everything is written against a numerical module `xp`, so one set of formulas
serves numpy (the whole DOE grid in one broadcast) and jax.numpy (the
derivatives the sensitivity stage takes).

Where each number comes from
----------------------------
Rocks. `range_doe.scatter` draws footprint diameters uniformly in
[size (1 - jitter), size (1 + jitter)] with size 2.0 m and jitter 0.5 by
default, and places rocks until their footprints cover `density` of the
terrain. The mean footprint is pi/4 E[d^2] = pi/4 size^2 (1 + jitter^2 / 3), so
the rock count per square metre is density / that. No rock is dealt a cell
within `--agr-keepout-radius` (3 m) of the start, so inside the start area of
radius R the rock rate is scaled by 1 - (3 / R)^2.

Encounters. The trial counts an obstacle as encountered when the AGR passes
within 1.5 m of its centre (`perfect/examples/isaacsim-range/sim_trial.py`), so
a straight path of length L sweeps a strip 3 m wide and meets
rate * 3 * L rock centres on average. The chance of at least one is
1 - exp(-rate * 3 * L).

Blocking. A rock blocks the path when its centre lies within half its diameter
plus half the AGR's wheel track of the centre line; the wheel track is 0.413 m,
the `wheelDistance` of the Carter v2.4 differential controller. Rocks are then a
Poisson field along the path with mean free path 1 / (rate * (E[d] + track)),
and the expected distance before the first block, over a commanded path of
L = 0.6 m/s * 30 s = 18 m, is mfp * (1 - exp(-L / mfp)). A block with
restitution e sends the AGR back at e times its approach speed, and dynamic
friction mu_d stops it after (e v)^2 / (2 mu_d g).

Grade. `range_doe.slope_scale_for` scales the terrain height by
k = tan(target) / g99, where g99 is the 99th percentile of the unscaled height
gradient on the 4.8 cm grid. The same k scales every gradient, so the grade the
AGR meets is atan(k * g) on the grid it climbs on: the gradient of the height
averaged into 16 x 16 blocks (77 cm, `Terrain.gradient(window=16)`), inside the
disc of radius 6 m around the start (-18.75, -5.31) that every recorded
traverse stayed in. The authored terrain is k = 1.

Traction. A wheel on grade theta holds without sliding while
mu_s >= tan(theta). The no-slip margin is mu_s - tan(p90 grade); the slip share
is the part of the start area's climbing demand, mean((k g - mu_s)+) / mean(k g),
that the friction cannot hold. The model takes the terrain material's mu_s as
the contact's; PhysX combines it with the wheel material's own.

Scores. Contestedness is the mean of three shares in [0, 1]: the chance of at
least one obstacle encounter, the relief (each cell's grade as a share of the
0.35 rad, 20.05 degree, attitude bound in
`veritas/runtime/stl-observer/specs/range_safety.yaml`, capped at 1 and
averaged) and the slip share. Predicted traversability is the product of the
expected progress fraction, the grip share (1 - slip share) and the attitude
share (1 at or below the bound, falling linearly to 0 at twice the bound,
averaged over the start area).
"""

import json
import math
import pathlib

import numpy as np

ROOT = pathlib.Path(__file__).resolve().parents[2]
TERRAIN_DIR = ROOT / "isaacsim" / "range" / "terrain"

# range_doe.py defaults and the isaacsim-range example's template
ROCK_SIZE = 2.0
ROCK_JITTER = 0.5
KEEPOUT_RADIUS = 3.0
START = (-18.75, -5.31)
SPEED = 0.6
DURATION = 30.0
PATH_LENGTH = SPEED * DURATION
# sim_trial.py
ENCOUNTER_RADIUS = 1.5
# the Carter v2.4 differential controller
WHEEL_TRACK = 0.413
# the start area and the grid a wheel climbs on
START_RADIUS = 6.0
WHEEL_WINDOW = 16
SLOPE_WINDOW = 1
SLOPE_PERCENTILE = 99.0
# the attitude bound of range_safety.yaml, 0.35 rad
ATTITUDE_BOUND_DEG = math.degrees(0.35)
GRAVITY = 9.81
# the translate on /World/terrain1_world in isaacsim/range/sim_world2.usd, as
# range_doe.base_offset reads it
BASE_OFFSET = (1.0, 1.0, 0.0)

MEAN_DIAMETER = ROCK_SIZE
MEAN_FOOTPRINT = math.pi / 4 * ROCK_SIZE ** 2 * (1 + ROCK_JITTER ** 2 / 3)
KEEPOUT_FACTOR = 1 - (KEEPOUT_RADIUS / START_RADIUS) ** 2


# ------------------------------------------------------------------
# the heightmap

def load_terrain(terrain_dir=TERRAIN_DIR):
    """The height grid and its world transform, as range_doe.Terrain builds it."""
    terrain_dir = pathlib.Path(terrain_dir)
    h = np.load(terrain_dir / "heightmap.npz")["height"].astype(np.float64)
    meta = json.loads((terrain_dir / "terrain_meta.json").read_text())
    m = meta["scene_xform"]["obj_to_world"]
    return {
        "h": h,
        "x0": m["x_offset"] + m["x_from_obj_x"] * meta["x0"] + BASE_OFFSET[0],
        "y0": m["y_offset"] + m["y_from_obj_z"] * meta["z0"] + BASE_OFFSET[1],
        "dx": m["x_from_obj_x"] * meta["dx"],
        "dy": m["y_from_obj_z"] * meta["dz"],
        "hz": m["z_from_obj_y"],
    }


def gradient(terrain, window=1):
    """|grad h| of the unscaled world height, the formula of range_doe.Terrain.gradient.

    Returns (g, x, y): the gradient per cell and the world position of each
    cell, where a cell sits between two block centres on each axis.
    """
    H = terrain["h"] * terrain["hz"]
    sx, sy = abs(terrain["dx"]), abs(terrain["dy"])
    rows, cols = H.shape
    if window > 1:
        r, c = (rows // window) * window, (cols // window) * window
        H = H[:r, :c].reshape(r // window, window, c // window, window).mean((1, 3))
        sx, sy = sx * window, sy * window
    gx = ((H[1:, :-1] + H[1:, 1:]) - (H[:-1, :-1] + H[:-1, 1:])) / (2 * sx)
    gy = ((H[:-1, 1:] + H[1:, 1:]) - (H[:-1, :-1] + H[1:, :-1])) / (2 * sy)
    row = (np.arange(gx.shape[0]) + 1) * window - 0.5
    col = (np.arange(gx.shape[1]) + 1) * window - 0.5
    x = terrain["x0"] + terrain["dx"] * row
    y = terrain["y0"] + terrain["dy"] * col
    X, Y = np.meshgrid(x, y, indexing="ij")
    return np.hypot(gx, gy), X, Y


def slope_reference(terrain):
    """g99: the unscaled gradient percentile that `--max-slope-deg` targets."""
    g, _, _ = gradient(terrain, SLOPE_WINDOW)
    return float(np.percentile(g, SLOPE_PERCENTILE))


def start_area(terrain, start=START, radius=START_RADIUS, window=WHEEL_WINDOW):
    """Unscaled wheel-scale gradients of the cells within `radius` of the start."""
    g, x, y = gradient(terrain, window)
    inside = np.hypot(x - start[0], y - start[1]) <= radius
    return g[inside]


def height_scale(slope_deg, g99, xp=np):
    """The k range_doe.py writes for a slope target, in degrees."""
    return xp.tan(xp.radians(slope_deg)) / g99


def context(terrain_dir=TERRAIN_DIR):
    """The two heightmap quantities the model needs: g99 and the start-area cells."""
    terrain = load_terrain(terrain_dir)
    g = start_area(terrain)
    return {"g99": slope_reference(terrain), "cells": g,
            "cells_p90": float(np.percentile(g, 90))}


# ------------------------------------------------------------------
# the attributes

def attributes(density, k, mu_s, mu_d, restitution, cells, cells_p90, xp=np):
    """Every analytic attribute of a range configuration.

    The five knobs broadcast against each other (a whole grid at once); `cells`
    are the start area's unscaled gradients and ride on a trailing axis.
    `density` must be above zero.
    """
    density = xp.asarray(density, dtype=float)
    k = xp.asarray(k, dtype=float)
    mu_s = xp.asarray(mu_s, dtype=float)
    mu_d = xp.asarray(mu_d, dtype=float)
    restitution = xp.asarray(restitution, dtype=float)
    L = PATH_LENGTH

    rate = density / MEAN_FOOTPRINT * KEEPOUT_FACTOR
    encounters_per_m = rate * 2 * ENCOUNTER_RADIUS
    p_encounter = 1 - xp.exp(-encounters_per_m * L)
    blocks_per_m = rate * (MEAN_DIAMETER + WHEEL_TRACK)
    p_block = 1 - xp.exp(-blocks_per_m * L)
    slide_back = (restitution * SPEED) ** 2 / (2 * mu_d * GRAVITY)
    progress = xp.maximum(p_block * (1 / blocks_per_m - slide_back), 0.0) / L

    t = k[..., None] * cells
    theta = xp.degrees(xp.arctan(t))
    grade_mean = theta.mean(-1)
    grade_p90 = xp.degrees(xp.arctan(k * cells_p90))
    margin = mu_s - k * cells_p90
    slip = xp.maximum(t - mu_s[..., None], 0.0).mean(-1) / t.mean(-1)
    relief = xp.minimum(theta / ATTITUDE_BOUND_DEG, 1.0).mean(-1)
    attitude = 1 - xp.clip((theta - ATTITUDE_BOUND_DEG) / ATTITUDE_BOUND_DEG, 0.0, 1.0).mean(-1)

    contested = (p_encounter + relief + slip) / 3
    traversable = progress * (1 - slip) * attitude
    return {
        "rocks_per_m2": density / MEAN_FOOTPRINT,
        "encounters_per_m": encounters_per_m,
        "p_encounter": p_encounter,
        "mean_free_path_m": 1 / blocks_per_m,
        "progress_fraction": progress,
        "grade_mean_deg": grade_mean,
        "grade_p90_deg": grade_p90,
        "no_slip_margin": margin,
        "slip_share": slip,
        "relief": relief,
        "attitude": attitude,
        "contestedness": contested,
        "traversability": traversable,
    }


def scores(knobs, ctx, xp=np):
    """(contestedness, traversability) of knobs = (density, slope_deg, mu_s, mu_d, restitution).

    `knobs` has the five knobs on its last axis. This is the form the
    derivatives are taken of.
    """
    k = height_scale(knobs[..., 1], ctx["g99"], xp)
    a = attributes(knobs[..., 0], k, knobs[..., 2], knobs[..., 3], knobs[..., 4],
                   xp.asarray(ctx["cells"]), ctx["cells_p90"], xp)
    return a["contestedness"], a["traversability"]


KNOBS = ["obstacle_density", "max_slope_deg", "friction_static", "friction_dynamic",
         "restitution"]


def relative_sensitivities(points, ctx):
    """x * d(score)/dx for every point and knob, by JAX forward mode.

    points: (n, 5) knob rows. Returns (dC, dT), each (n, 5).
    """
    import os
    # the derivatives are small; keep JAX off the GPU and quiet about it
    os.environ.setdefault("JAX_PLATFORMS", "cpu")
    from tradesx.sensitivity import _jax
    jax = _jax()
    import jax.numpy as jnp
    x = jnp.asarray(points, dtype=float)
    jc = jax.vmap(jax.jacfwd(lambda p: scores(p, ctx, jnp)[0]))(x)
    jt = jax.vmap(jax.jacfwd(lambda p: scores(p, ctx, jnp)[1]))(x)
    return np.asarray(jc) * np.asarray(points), np.asarray(jt) * np.asarray(points)


def relative_sensitivities_fd(points, ctx, rel_step=1e-6):
    """The same by central differences, all points and knobs in two evaluations."""
    x = np.asarray(points, dtype=float)
    n, m = x.shape
    h = rel_step * np.maximum(np.abs(x), 1.0)
    e = np.eye(m)[None, :, :] * h[:, None, :]
    up = scores(x[:, None, :] + e, ctx)
    down = scores(x[:, None, :] - e, ctx)
    dc = (up[0] - down[0]) / (2 * h)
    dt = (up[1] - down[1]) / (2 * h)
    return dc * x, dt * x
