"""Grid planner and the closed loop.

The planner is a grid wavefront: the cost-to-go field from the goal over an
8-connected occupancy grid, computed by relaxation sweeps that are whole-array
numpy operations over the whole batch of episodes at once. The robot then
descends that field one cell per control step. This is the same shortest-path
field A* would search, computed without a per-cell priority queue so that K
episodes are planned in one call.

The robot is a square footprint of half side world.ROBOT_HALF. Every arm,
conformal or not, grows the obstacles it plans against by that half side, which
is the usual configuration-space inflation a Nav2 costmap applies; the conformal
quantile q is the extra margin on top, and it is the only difference between the
arms. A collision is the footprint overlapping a true box, which for square
boxes and a square footprint is the robot centre entering the true box grown by
ROBOT_HALF.

The closed loop at every step: detect, inflate by ROBOT_HALF + q, rasterise,
recompute the cost-to-go, move one cell, check the move against the TRUE boxes
grown by ROBOT_HALF. An episode
ends as SUCCESS (goal cell reached), COLLISION (the swept step crosses a true
box) or STALLED (the step budget ran out). When the inflated detections leave no
finite cost-to-go the robot waits in place for that step, which is how the
conservativeness of a large inflation shows up: more waits, longer paths and
eventually a timeout.

The only interpreter loops here are over control steps, over relaxation sweeps
and over the eight neighbour offsets. Every array operation inside them runs
over the full (episode, row, column) batch.
"""

import numpy as np

from . import conformal, detector, world

RUNNING, SUCCESS, COLLISION, STALLED = 0, 1, 2, 3

NEIGHBOURS = np.array(
    [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]
)
STEP_COST = np.hypot(NEIGHBOURS[:, 0], NEIGHBOURS[:, 1]) * world.RES

SWEEP_POINTS = 5       # samples along a step, for the collision test
MAX_SWEEPS = 300       # relaxation iterations before giving up on convergence


def rasterise(boxes, valid):
    """Occupancy grid of a batch of box sets. (K, M, 4), (K, M) -> (K, H, W) bool."""
    xs = world.cell_centres()
    in_x = (boxes[:, :, None, 0] <= xs) & (xs <= boxes[:, :, None, 2])
    in_y = (boxes[:, :, None, 1] <= xs) & (xs <= boxes[:, :, None, 3])
    hit = in_y[:, :, :, None] & in_x[:, :, None, :] & valid[:, :, None, None]
    return np.any(hit, axis=1)


def cost_to_go(occ, goal_rc=world.GOAL_RC):
    """Cost-to-go from every free cell to the goal. (K, H, W) bool -> (K, H, W).

    Relaxation sweeps: every sweep takes, for each cell, the least of its own
    value and each neighbour's value plus the step cost, then re-blocks the
    occupied cells. The fixed point is the 8-connected shortest-path cost, the
    same field A* would search. The sweep runs over the whole batch at once and
    the buffers are allocated once, so the only interpreter loops are over
    sweeps and over the eight neighbour offsets.
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
            np.add(pad[:, 1 + dr : 1 + dr + h, 1 + dc : 1 + dc + w], np.float32(c), out=work)
            np.minimum(nxt, work, out=nxt)
        np.copyto(nxt, inf, where=occ)
        if np.array_equal(nxt, d):
            break
        d, nxt = nxt, d
    return d


def _best_move(d, rc):
    """Neighbour of each robot cell with the least total cost. rc (K, 2) int."""
    k, h, w = d.shape
    cand = rc[:, None, :] + NEIGHBOURS[None, :, :]
    ok = np.all((cand >= 0) & (cand < np.array([h, w])), axis=2)
    vals = d[np.arange(k)[:, None], np.clip(cand[:, :, 0], 0, h - 1), np.clip(cand[:, :, 1], 0, w - 1)]
    total = np.where(ok, vals + STEP_COST[None, :], np.inf)
    pick = np.argmin(total, axis=1)
    return cand[np.arange(k), pick], total[np.arange(k), pick]


def run_episodes(rng, boxes, valid, hard, q, max_steps=120, shift=0.0, record=False,
                 on_step=None):
    """Run the closed loop for a batch of worlds.

    q is the conformal inflation per episode, broadcast to (K,); q = 0 is the
    nominal arm, which uses the raw detections. Returns a dict with the status,
    the path length, the realised trajectory, the number of steps, and, when
    `record` is set, the per-detection rows and the last frame of boxes.

    `on_step(state)`, when given, is called at the end of every control step with
    a dict of the batch arrays of that step: the step index `t`, the pose and
    grid cell before the move (`xy_before`, `rc_before`), the detections
    (`det`, `det_valid`), the regions planned against (`regions`, the detections
    grown by ROBOT_HALF + q), the cost-to-go field `cost_to_go`, the pose after
    the move `xy`, and `status` after the step. It draws nothing from `rng`, so
    a run with the hook is the same run.
    """
    k = boxes.shape[0]
    q = np.broadcast_to(np.asarray(q, dtype=float), (k,))
    rc = np.tile(np.array(world.START_RC), (k, 1))
    xy = np.tile(world.START_XY, (k, 1))
    goal_xy = world.GOAL_XY

    footprint_boxes = conformal.inflate(boxes, world.ROBOT_HALF)
    status = np.full(k, RUNNING)
    length = np.zeros(k)
    steps = np.zeros(k, dtype=int)
    waits = np.zeros(k, dtype=int)
    traj = [xy.copy()]
    rows = []
    frames = []

    for t in range(max_steps):
        live = status == RUNNING
        if not live.any():
            break

        det, det_valid, dist = detector.detect(rng, boxes, valid, hard, xy, shift=shift)
        if record:
            # only episodes still running contribute rows: a finished episode is
            # frozen at its terminal pose and would flood the table with repeats
            rows.append(_rows(t, boxes, det, det_valid & live[:, None], dist, xy))
            frames.append((det.copy(), conformal.inflate(det, world.ROBOT_HALF + q[:, None]).copy(), det_valid.copy()))

        regions = conformal.inflate(det, world.ROBOT_HALF + q[:, None])
        occ = rasterise(regions, det_valid)
        occ[np.arange(k), rc[:, 0], rc[:, 1]] = False    # never fence the robot in
        d = cost_to_go(occ)
        xy_before, rc_before = xy, rc
        nxt, total = _best_move(d, rc)

        stuck = live & ~np.isfinite(total)
        waits = waits + stuck
        moved = live & ~stuck

        nxt_xy = (nxt[:, ::-1] + 0.5) * world.RES
        frac = np.linspace(0.0, 1.0, SWEEP_POINTS)[None, :, None]
        swept = xy[:, None, :] + frac * (nxt_xy - xy)[:, None, :]
        crash = moved & world.inside_any(footprint_boxes, valid, swept).any(axis=1)

        length = length + np.where(moved, np.linalg.norm(nxt_xy - xy, axis=1), 0.0)
        steps = steps + moved
        xy = np.where(moved[:, None], nxt_xy, xy)
        rc = np.where(moved[:, None], nxt, rc)
        traj.append(xy.copy())

        status = np.where(crash, COLLISION, status)
        reached = (status == RUNNING) & (np.linalg.norm(xy - goal_xy, axis=1) < world.RES)
        status = np.where(reached, SUCCESS, status)
        if on_step is not None:
            on_step({"t": t, "xy_before": xy_before, "rc_before": rc_before, "det": det,
                     "det_valid": det_valid, "regions": regions, "cost_to_go": d,
                     "xy": xy, "status": status})

    status = np.where(status == RUNNING, STALLED, status)
    out = {
        "status": status,
        "length": length,
        "steps": steps,
        "waits": waits,
        "traj": np.stack(traj, axis=1),
        "q": np.array(q),
    }
    if record:
        out["rows"] = np.concatenate(rows, axis=0) if rows else np.zeros((0, 14))
        out["frames"] = frames
    return out


def _rows(t, boxes, det, det_valid, dist, xy):
    """Per-detection rows of one frame, flattened to (n_valid, 14)."""
    k, m = det_valid.shape
    ep, obj = np.nonzero(det_valid)
    cols = [
        ep,
        np.full(ep.shape, t),
        obj,
        xy[ep, 0],
        xy[ep, 1],
        dist[ep, obj],
        boxes[ep, obj, 0], boxes[ep, obj, 1], boxes[ep, obj, 2], boxes[ep, obj, 3],
        det[ep, obj, 0], det[ep, obj, 1], det[ep, obj, 2], det[ep, obj, 3],
    ]
    return np.stack(cols, axis=1)


ROW_COLUMNS = [
    "episode", "step", "object", "robot_x", "robot_y", "range",
    "true_xmin", "true_ymin", "true_xmax", "true_ymax",
    "det_xmin", "det_ymin", "det_xmax", "det_ymax",
]


def descend(d, rc, max_len=4 * world.NCELL):
    """The path the robot would follow down a fixed cost-to-go field.

    d (K, H, W), rc (K, 2) int. Repeats the control loop's own move rule from rc
    until the goal cell (cost 0) or a cell with no finite way on. Returns the
    cells (K, L, 2) and the number of cells in use per episode (K,); the rows of
    an episode that stopped early repeat its last cell. The loop is over path
    steps; each step moves the whole batch.
    """
    k = d.shape[0]
    cells = [rc]
    going = np.isfinite(d[np.arange(k), rc[:, 0], rc[:, 1]]) & (d[np.arange(k), rc[:, 0], rc[:, 1]] > 0)
    used = np.ones(k, dtype=int)
    for _ in range(max_len):
        if not going.any():
            break
        nxt, total = _best_move(d, cells[-1])
        going = going & np.isfinite(total)
        cur = np.where(going[:, None], nxt, cells[-1])
        used = used + going
        cells.append(cur)
        going = going & (d[np.arange(k), cur[:, 0], cur[:, 1]] > 0)
    return np.stack(cells, axis=1), used
