"""The tree of one planner run, kept at chosen iterations.

`plan` calls its `on_iteration` hook with the live tree buffers; this module
copies them out at the iterations asked for and rebuilds, from any kept tree,
the path `plan` would return if it stopped there.  Used by
animations/make_rarrt_tree_growth.py.
"""

import numpy as np

from rarrt.rrtstar import plan


def record_growth(world, cost, at, **plan_kwargs):
    """Run `plan` once and keep the tree before each iteration listed in `at`.

    An entry equal to the iteration count keeps the final tree.  Returns the
    planner's result and a list of snapshots, each a dict with the iteration,
    the node points (n, 2), the parent indices (n,) and the cost-to-come (n,).
    """
    wanted = set(int(i) for i in np.atleast_1d(at))
    snapshots = []

    def keep(i, n, pts, parent, cost_to):
        if i in wanted:
            snapshots.append({"iteration": i, "points": pts[:n].copy(),
                              "parent": parent[:n].copy(), "cost_to": cost_to[:n].copy()})

    result = plan(world, cost, on_iteration=keep, **plan_kwargs)
    return result, snapshots


def best_path(world, cost, points, parent, cost_to, step):
    """The path to the goal through a kept tree, by the rule `plan` ends with.

    The goal is joined from every node within twice the step whose segment to it
    is free, and the node with the least cost-to-come plus that segment's cost
    wins.  Returns (path (m, 2), cost), or (None, inf) when no node connects.
    """
    to_goal = np.linalg.norm(points - world.goal, axis=1)
    reachable = np.nonzero(to_goal <= 2.0 * step)[0]
    if reachable.size == 0:
        return None, np.inf
    clearance = world.segment_clearance(points[reachable],
                                        np.broadcast_to(world.goal, (reachable.size, 2)))
    total = np.where(clearance > 0.0,
                     cost_to[reachable] + cost.edge_cost(to_goal[reachable], clearance),
                     np.inf)
    best = int(np.argmin(total))
    if not np.isfinite(total[best]):
        return None, np.inf
    chain = [int(reachable[best])]
    while parent[chain[-1]] >= 0:
        chain.append(int(parent[chain[-1]]))
    return np.vstack([points[chain[::-1]], world.goal]), float(total[best])
