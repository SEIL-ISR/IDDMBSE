"""The PERFECT-shaped data generator.

In the lab this is a PERFECT campaign: the full perception-and-planning stack is
run across the contested-terrain range, and every trial writes back labelled,
closed-loop data. Here the same job is done by running the nominal closed loop
(no inflation) over randomly drawn worlds and recording, for every frame, one
row per detection with the ground-truth box beside it.

The table written by `write_rows` has the shape a PERFECT Trial result would
carry: flat per-detection rows keyed by the episode (the Trial) and the step
(the frame inside the Trial), so a real campaign's export drops into the rest of
this case study unchanged. Only the source of the rows is synthetic.

Calibration data must come from the closed-loop states the robot actually
visits, which is why the campaign runs the planner rather than sampling boxes in
the abstract, and why `shift` is exposed: re-running the campaign under a
deliberate shift in clutter or lighting is what the paper asks PERFECT for.
"""

import numpy as np

from . import conformal, planner, world


def feasible_worlds(rng, n, oversample=2.0):
    """Draw n worlds in which the goal is reachable given the TRUE boxes.

    A world that is blocked even with perfect perception says nothing about the
    detector, so it is dropped here rather than counted as a navigation failure.
    """
    m = int(np.ceil(n * oversample)) + 16
    boxes, valid, hard = world.sample_worlds(rng, m)
    grown = conformal.inflate(boxes, world.ROBOT_HALF)
    d = planner.cost_to_go(planner.rasterise(grown, valid))
    ok = np.isfinite(d[:, world.START_RC[0], world.START_RC[1]])
    keep = np.nonzero(ok)[0][:n]
    if keep.size < n:
        raise RuntimeError("not enough feasible worlds: got " + str(keep.size) + " of " + str(n))
    return boxes[keep], valid[keep], hard[keep]


def run_campaign(rng, n_episodes, shift=0.0, every=1):
    """Run the nominal closed loop over n_episodes worlds and return the rows.

    `every` keeps one frame in `every` to hold the table down; the rows kept are
    still whole frames, so the per-frame structure is preserved.
    """
    boxes, valid, hard = feasible_worlds(rng, n_episodes)
    out = planner.run_episodes(rng, boxes, valid, hard, q=0.0, shift=shift, record=True)
    rows = out["rows"]
    rows = rows[np.mod(rows[:, 1], every) == 0]
    return rows, out


def write_rows(path, rows):
    header = ",".join(planner.ROW_COLUMNS)
    np.savetxt(path, rows, delimiter=",", header=header, comments="", fmt="%.4f")


def read_rows(path):
    return np.loadtxt(path, delimiter=",", skiprows=1)


def split_by_episode(rows, n_cal_episodes):
    """Calibration and held-out rows, split on the episode id.

    Rows inside one episode are not exchangeable with each other (consecutive
    frames see the same objects from nearby poses), so the split is taken over
    whole episodes, not over rows.
    """
    ep = rows[:, 0]
    return rows[ep < n_cal_episodes], rows[ep >= n_cal_episodes]


def boxes_from_rows(rows):
    """True and detected boxes out of a row table. -> (n, 4), (n, 4)."""
    return rows[:, 6:10], rows[:, 10:14]
