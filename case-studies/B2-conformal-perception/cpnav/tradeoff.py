"""The TRADES-X hook: the coverage level as a design variable.

TRADES-X treats 1 - alpha as a design variable and trades it against navigation
conservativeness. `sweep` evaluates one arm per alpha plus a nominal arm on the
same set of worlds, all in a single batched closed-loop call: the arms are
stacked along the episode axis and each carries its own inflation q.

The columns it returns are the trade-off table: coverage (the assurance bought),
collision rate (the safety it buys), and success rate, mean path length and mean
waiting steps (the conservativeness it costs).
"""

import numpy as np

from . import planner


def sweep(rng, boxes, valid, hard, qs, shift=0.0):
    """Run one arm per entry of qs on the same worlds.

    Returns the trade-off rows and the raw batched result, whose per-episode
    fields are laid out arm-major so that `field.reshape(len(qs), -1)` splits
    them back out.
    """
    qs = np.asarray(qs, dtype=float)
    a = qs.size
    k = boxes.shape[0]
    out = planner.run_episodes(
        rng,
        np.tile(boxes, (a, 1, 1)),
        np.tile(valid, (a, 1)),
        np.tile(hard, (a, 1)),
        q=np.repeat(qs, k),
        shift=shift,
    )
    status = out["status"].reshape(a, k)
    length = out["length"].reshape(a, k)
    waits = out["waits"].reshape(a, k)
    ok = status == planner.SUCCESS
    rows = [
        {
            "q": float(qs[i]),
            "success_rate": float(ok[i].mean()),
            "collision_rate": float((status[i] == planner.COLLISION).mean()),
            "stall_rate": float((status[i] == planner.STALLED).mean()),
            "mean_path_length": float(length[i][ok[i]].mean()) if ok[i].any() else float("nan"),
            "mean_waits": float(waits[i].mean()),
        }
        for i in range(a)
    ]
    return rows, out
