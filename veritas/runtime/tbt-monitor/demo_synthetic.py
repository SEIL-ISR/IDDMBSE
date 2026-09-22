"""Drive the behavior-tree monitor on a hand-made pick-and-place trace.

Same monitor (tbt_monitor.compose_seq) and same leaf specifications
(panda_specifications) as the RL rollout in main.py, but the signals come from a
synthetic trajectory instead of panda-gym, so this runs on the base install: no torch,
no simulator, no display.

Each row of the trace is the signal vector main.py builds in
STLMonitorWrapper.get_signals: [distance to object, gripper width, distance to goal,
is_success]. The behavior tree is Sequence(reach object, grasp, reach goal), and the
leaf specifications are eventually(d2obj < 0.1), eventually(width < 0.05) and
eventually(d2goal < 0.05).

The step loop below is the online-monitoring protocol, not array arithmetic: the monitor
is stateful and the slice each leaf sees depends on when the previous leaf succeeded, so
the calls cannot be batched. The trajectory itself is built with whole-array numpy.
"""

import numpy as np

from panda_specifications import evaluate, evaluate_reach_object, evaluate_grasp, evaluate_reach_goal
from tbt_monitor import compose_seq

n_reach, n_grasp, n_place = 8, 6, 12


def make_trace(grasp_closes=True):
    d2obj = np.concatenate([
        np.round(np.linspace(0.30, 0.04, n_reach), 3),
        np.full(n_grasp + n_place, 0.03)
    ])
    if grasp_closes:
        width = np.concatenate([
            np.full(n_reach, 0.08),
            np.round(np.linspace(0.08, 0.01, n_grasp), 3),
            np.full(n_place, 0.01)
        ])
    else:
        width = np.full(n_reach + n_grasp + n_place, 0.08)
    d2goal = np.concatenate([
        np.full(n_reach + n_grasp, 0.30),
        np.round(np.linspace(0.30, 0.01, n_place), 3)
    ])
    is_success = (d2goal < 0.05).astype(float)
    return np.stack([d2obj, width, d2goal, is_success], axis=1)


def run(trace):
    """Feed the trace to a fresh monitor one step at a time, as main.py does.

    Returns the list of (rho, state) pairs, one per step from the second step on
    (main.py skips the first step, where a one-row window has no robustness).
    """

    tbt = compose_seq(evaluate_reach_object, evaluate_grasp, evaluate_reach_goal)
    return [evaluate(tbt, trace[:k + 1]) for k in range(1, len(trace))]


def report(label, trace):
    print(label)
    out = run(trace)
    for k, (rho, state) in enumerate(out, start=1):
        print("step", k, "rho", round(float(rho), 4), "state", state)
    print("final rho", round(float(out[-1][0]), 4), "final state", out[-1][1])
    print()
    return out


report("trace 1: reach, grasp, place", make_trace(grasp_closes=True))
report("trace 2: reach, never grasp", make_trace(grasp_closes=False))
