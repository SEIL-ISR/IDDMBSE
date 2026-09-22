"""A planar navigation simulation whose outcome depends on the sensor suite.

A ground robot crosses a square field of rocks from one corner to the other. It
only avoids a rock once one of its sensors has reported it, so the suite decides
how early the map fills in, how far the robot detours, and whether it arrives.

The grid wavefront and the closed-loop shape are taken from
`case-studies/B2-conformal-perception/cpnav/planner.py` in this repository:
the cost-to-go field from the goal over an 8-connected occupancy grid, computed
by relaxation sweeps that are whole-array operations over the whole batch of
noise draws at once, with the robot descending that field one cell per control
step. Numbers, the sensing model and the metrics are this example's own.

What a sensor is here
---------------------
Update rate, horizontal field of view, horizontal angular resolution, maximum
range, and whether ambient light matters to it. A sensor reports a rock of
radius r at distance d with probability

    p = exp(-d / L),   L = 2 * r / (SAMPLES_TO_RESOLVE * ares)

when the rock is inside the sensor's field of view and inside its maximum
range, and 0 otherwise. L is the distance at which the rock stops covering
SAMPLES_TO_RESOLVE of the sensor's angular samples, so a finer angular
resolution or a bigger rock pushes it out. For a light-sensitive sensor the
scenario's visibility v in (0, 1] both scales the maximum range and multiplies
p, so a camera loses most of its reach in the dark while a lidar does not
notice.

One control step is longer than one sensor frame, so a sensor gets several
looks per step. Repeated looks at a static rock are strongly correlated, so the
effective number of independent looks is (rate * dt) ** LOOK_EXPONENT rather
than rate * dt, and the per-step probability for the whole suite is

    1 - prod_s (1 - p_s) ** n_s

A rock, once reported, stays on the map.

Why the suite changes the outcome
---------------------------------
The global planner runs every PLAN_PERIOD control steps, as a real one does,
and between plans the robot follows the field it last computed. A rock the map
did not hold when that plan was made is a rock the robot can drive into. So a
suite that reports rocks early leaves the robot on a route close to the one it
would take knowing everything, and a suite that reports them late leaves it
detouring, backtracking, or hitting them.

Scenario parameters
-------------------
clutter     0..1, sets the rock count between MIN_ROCKS and MAX_ROCKS
visibility  0..1, ambient light; scales the light-sensitive sensors
seed        picks the rock field
n_draws     how many independent noise draws share that rock field

Batching
--------
The leading axis of every array is the noise draw. The only interpreter loops
are over control steps, over relaxation sweeps and over the eight neighbour
offsets; nothing loops over draws, rocks or sensors.

    python sensor_sim.py job.json metrics.json
"""

import json
import sys

import numpy as np

SIZE = 30.0            # field side, metres
RES = 0.5              # occupancy grid resolution, metres
NCELL = int(round(SIZE / RES))
START_RC = (4, 4)
GOAL_RC = (55, 55)

MIN_ROCKS = 12
MAX_ROCKS = 55
RADIUS = (0.6, 1.8)    # rock radius, metres, uniform
MARGIN = 2.0           # rock centres stay this far from the field edge
CLEARANCE = 1.5        # rocks this close to start or goal are dropped

ROBOT_HALF = 0.35      # half side of the robot footprint, metres
SPEED = 1.0            # metres per second

SAMPLES_TO_RESOLVE = 200  # angular samples a rock needs before a sensor reports it
LOOK_EXPONENT = 0.5       # correlated repeated looks: (rate * dt) ** this
PLAN_PERIOD = 6           # control steps between global re-plans

MAX_STEPS = 240
MAX_SWEEPS = 200
BATTERY_J = 6.0e4      # usable energy of the AGR battery pack, joules (16.7 Wh)

RUNNING, SUCCESS, COLLISION, STALLED = 0, 1, 2, 3

NEIGHBOURS = np.array([(-1, -1), (-1, 0), (-1, 1), (0, -1),
                       (0, 1), (1, -1), (1, 0), (1, 1)])
STEP_COST = np.hypot(NEIGHBOURS[:, 0], NEIGHBOURS[:, 1]) * RES

SWEEP_POINTS = 5       # samples along a step, for the collision test
PLAN_MARGIN = RES * np.sqrt(2) / 2   # half a cell diagonal, see inflated_discs


def cell_centres():
    return (np.arange(NCELL) + 0.5) * RES


def cell_xy(rc):
    r, c = rc
    return np.array([(c + 0.5) * RES, (r + 0.5) * RES])


START_XY = cell_xy(START_RC)
GOAL_XY = cell_xy(GOAL_RC)
CHORD = float(np.linalg.norm(GOAL_XY - START_XY))
TIME_BUDGET = MAX_STEPS * RES / SPEED
LENGTH_BUDGET = MAX_STEPS * RES


# ------------------------------------------------------------------
# the rock field

def rock_field(seed, clutter):
    """Rock centres (M, 2) and radii (M,) for one scenario.

    The field is a property of the environment, so every noise draw of a trial
    crosses the same rocks; what differs between draws is what the sensors
    report.
    """
    rng = np.random.default_rng(int(seed))
    n = int(round(MIN_ROCKS + float(np.clip(clutter, 0.0, 1.0)) * (MAX_ROCKS - MIN_ROCKS)))
    centre = rng.uniform(MARGIN, SIZE - MARGIN, size=(n, 2))
    radius = rng.uniform(RADIUS[0], RADIUS[1], size=n)
    keep = np.ones(n, dtype=bool)
    for anchor in (START_XY, GOAL_XY):
        keep &= np.linalg.norm(centre - anchor, axis=1) > radius + CLEARANCE
    return centre[keep], radius[keep]


def inflated_discs(centre, radius):
    """(M, H*W) float32: 1 where a cell centre lies in a rock the robot must avoid.

    A rock is grown by the robot's half footprint, the usual configuration-space
    inflation a Nav2 costmap applies, and by PLAN_MARGIN on top. The margin is
    there because the collision test is run on the continuous segment between
    two cell centres while the planner only tests cell centres: without it a
    route through cells the planner calls free can still clip a rock by up to
    half a diagonal, and a robot that knew the whole field would still crash.
    """
    xs = cell_centres()
    dx = xs[None, None, :] - centre[:, 0, None, None]
    dy = xs[None, :, None] - centre[:, 1, None, None]
    grown = (radius + ROBOT_HALF + PLAN_MARGIN)[:, None, None]
    return ((dx * dx + dy * dy) <= grown * grown).reshape(len(centre), -1).astype(np.float32)


# ------------------------------------------------------------------
# the sensor suite

def suite_arrays(suite, visibility):
    """Per-sensor arrays for the detection model, all shape (S,)."""
    if not suite:
        z = np.zeros(0)
        return z, z, z, z, z
    rate = np.array([s["update_rate"] for s in suite], dtype=float)
    h_fov = np.array([s["h_fov"] for s in suite], dtype=float)
    ares = np.array([s["ares"] for s in suite], dtype=float)
    reach = np.array([s["max_range"] for s in suite], dtype=float)
    light = np.array([s["light_sensitive"] for s in suite], dtype=float)
    v = float(np.clip(visibility, 0.0, 1.0))
    gain = np.where(light > 0, v, 1.0)
    return rate, h_fov, ares, reach * gain, gain


def suite_totals(suite):
    """Price, electrical power and buffer RAM of the whole suite."""
    return (sum(s["cost"] for s in suite),
            sum(s["power"] for s in suite),
            sum(s["ram"] for s in suite))


def report_probability(dist, bearing, radius, rate, h_fov, ares, reach, gain, dt):
    """Per-step probability that the suite reports each rock. (K, M) out.

    dist and bearing are (K, M); heading is already subtracted from bearing.
    """
    k, m = dist.shape
    if rate.size == 0:
        return np.zeros((k, m))
    d = dist[:, :, None]
    length = 2.0 * radius[None, :, None] / (SAMPLES_TO_RESOLVE * ares[None, None, :])
    p = np.exp(-d / length) * gain[None, None, :]
    in_fov = np.abs(bearing)[:, :, None] <= 0.5 * h_fov[None, None, :]
    p = np.where(in_fov & (d <= reach[None, None, :]), p, 0.0)
    looks = np.maximum(rate * dt, 1.0) ** LOOK_EXPONENT
    return 1.0 - np.prod((1.0 - p) ** looks[None, None, :], axis=2)


# ------------------------------------------------------------------
# the planner: cost-to-go by relaxation sweeps, over the whole batch at once

def cost_to_go(occ, goal_rc=GOAL_RC):
    """Cost-to-go from every free cell to the goal. (K, H, W) bool -> (K, H, W).

    Every sweep takes, for each cell, the least of its own value and each
    neighbour's value plus the step cost, then re-blocks the occupied cells.
    The fixed point is the 8-connected shortest-path cost. The sweep runs over
    the whole batch at once and the buffers are allocated once, so the only
    interpreter loops are over sweeps and over the eight neighbour offsets.
    """
    k, h, w = occ.shape
    inf = np.float32(np.inf)
    d = np.full((k, h, w), inf, dtype=np.float32)
    d[:, goal_rc[0], goal_rc[1]] = 0.0
    np.copyto(d, inf, where=occ)

    pad = np.full((k, h + 2, w + 2), inf, dtype=np.float32)
    work = np.empty((k, h, w), dtype=np.float32)
    nxt = np.empty((k, h, w), dtype=np.float32)
    for _ in range(MAX_SWEEPS):
        pad[:, 1:-1, 1:-1] = d
        np.copyto(nxt, d)
        for (dr, dc), c in zip(NEIGHBOURS, STEP_COST):
            np.add(pad[:, 1 + dr:1 + dr + h, 1 + dc:1 + dc + w], np.float32(c), out=work)
            np.minimum(nxt, work, out=nxt)
        np.copyto(nxt, inf, where=occ)
        if np.array_equal(nxt, d):
            break
        d, nxt = nxt, d
    return d


def best_move(d, rc):
    """Neighbour of each robot cell with the least total cost. rc (K, 2) int."""
    k, h, w = d.shape
    cand = rc[:, None, :] + NEIGHBOURS[None, :, :]
    ok = np.all((cand >= 0) & (cand < np.array([h, w])), axis=2)
    vals = d[np.arange(k)[:, None],
             np.clip(cand[:, :, 0], 0, h - 1),
             np.clip(cand[:, :, 1], 0, w - 1)]
    total = np.where(ok, vals + STEP_COST[None, :], np.inf)
    pick = np.argmin(total, axis=1)
    return cand[np.arange(k), pick], total[np.arange(k), pick]


# ------------------------------------------------------------------
# the closed loop

def simulate(suite, scenario):
    clutter = float(scenario.get("clutter", 0.4))
    visibility = float(scenario.get("visibility", 1.0))
    seed = int(scenario.get("seed", 1))
    k = max(1, int(scenario.get("n_draws", 8)))

    centre, radius = rock_field(seed, clutter)
    m = len(centre)
    disc = inflated_discs(centre, radius) if m else np.zeros((0, NCELL * NCELL), np.float32)
    rate, h_fov, ares, reach, gain = suite_arrays(suite, visibility)

    rng = np.random.default_rng(1000 * seed + 7)
    rc = np.tile(np.array(START_RC), (k, 1))
    xy = np.tile(START_XY, (k, 1))
    heading = np.full(k, np.arctan2(*(GOAL_XY - START_XY)[::-1]))

    known = np.zeros((k, m), dtype=bool)
    first_range = np.full((k, m), np.nan)
    status = np.full(k, RUNNING)
    length = np.zeros(k)
    elapsed = np.zeros(k)

    field = cost_to_go(np.zeros((k, NCELL, NCELL), dtype=bool))
    replans = 0
    pending = False

    for step_index in range(MAX_STEPS):
        live = status == RUNNING
        if not live.any():
            break

        if m:
            delta = centre[None, :, :] - xy[:, None, :]
            dist = np.linalg.norm(delta, axis=2)
            bearing = np.arctan2(delta[:, :, 1], delta[:, :, 0]) - heading[:, None]
            bearing = (bearing + np.pi) % (2 * np.pi) - np.pi
            dt = RES / SPEED
            p = report_probability(dist, bearing, radius, rate, h_fov, ares, reach, gain, dt)
            fresh = (rng.random((k, m)) < p) & ~known & live[:, None]
            first_range = np.where(fresh, dist, first_range)
            known = known | fresh
            pending = pending or bool(fresh.any())

        # The global planner runs at its own rate. Between plans the robot
        # follows the field it last computed, so a rock reported after the plan
        # was made is one the robot can still drive into.
        if pending and step_index % PLAN_PERIOD == 0:
            occ = (known.astype(np.float32) @ disc).reshape(k, NCELL, NCELL) > 0
            occ[np.arange(k), rc[:, 0], rc[:, 1]] = False   # never fence the robot in
            field = cost_to_go(occ)
            replans += 1
            pending = False

        nxt, total = best_move(field, rc)
        stuck = live & ~np.isfinite(total)
        moved = live & ~stuck

        nxt_xy = (nxt[:, ::-1] + 0.5) * RES
        step = nxt_xy - xy
        frac = np.linspace(0.0, 1.0, SWEEP_POINTS)[None, :, None]
        swept = xy[:, None, :] + frac * step[:, None, :]
        if m:
            gap = np.linalg.norm(swept[:, None, :, :] - centre[None, :, None, :], axis=3)
            crash = moved & (gap <= (radius + ROBOT_HALF)[None, :, None]).any(axis=(1, 2))
        else:
            crash = np.zeros(k, dtype=bool)

        travelled = np.linalg.norm(step, axis=1)
        length = length + np.where(moved, travelled, 0.0)
        elapsed = elapsed + np.where(live, np.where(moved, travelled, RES) / SPEED, 0.0)
        heading = np.where(moved, np.arctan2(step[:, 1], step[:, 0]), heading)
        xy = np.where(moved[:, None], nxt_xy, xy)
        rc = np.where(moved[:, None], nxt, rc)

        status = np.where(crash, COLLISION, status)
        reached = (status == RUNNING) & (np.linalg.norm(xy - GOAL_XY, axis=1) < RES)
        status = np.where(reached, SUCCESS, status)

    status = np.where(status == RUNNING, STALLED, status)
    return metrics(status, length, elapsed, first_range, known, suite,
                   clutter, visibility, seed, m, replans)


def metrics(status, length, elapsed, first_range, known, suite,
            clutter, visibility, seed, n_rocks, replans):
    """Per-trial metrics, averaged over the noise draws.

    A draw that collides or runs out of steps is charged the whole mission
    budget for its time and its path length, so that failing is never cheaper
    than arriving and the table stays finite when no draw arrives.
    """
    ok = status == SUCCESS
    time = np.where(ok, elapsed, TIME_BUDGET)
    path = np.where(ok, length, LENGTH_BUDGET)
    cost, power, ram = suite_totals(suite)
    seen = np.isfinite(first_range)
    soc = np.clip(1.0 - power * time / BATTERY_J, 0.0, 1.0)
    return {
        "n_draws": int(status.size),
        "n_sensors": len(suite),
        "n_rocks": int(n_rocks),
        "replans": int(replans),
        "success_rate": float(ok.mean()),
        "collision_rate": float((status == COLLISION).mean()),
        "stall_rate": float((status == STALLED).mean()),
        "time_to_goal": float(time.mean()),
        "path_length": float(path.mean()),
        "tortuosity": float((path / CHORD).mean()),
        "detection_rate": float(known.mean()) if known.size else 0.0,
        "detection_distance": float(first_range[seen].mean()) if seen.any() else 0.0,
        "battery_soc": float(soc.mean()),
        "sim_time": float(time.mean()),
        "cost": float(cost),
        "power": float(power),
        "ram": float(ram),
        "clutter": clutter,
        "visibility": visibility,
        "seed": seed,
    }


if __name__ == "__main__":
    job = json.load(open(sys.argv[1]))
    out = simulate(job.get("suite") or [], job.get("scenario") or {})
    with open(sys.argv[2], "w") as f:
        json.dump(out, f, indent=1)
    print("success_rate", round(out["success_rate"], 3),
          "time_to_goal", round(out["time_to_goal"], 2),
          "detection_distance", round(out["detection_distance"], 2))
