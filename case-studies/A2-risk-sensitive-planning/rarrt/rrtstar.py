"""RRT* with a pluggable edge-cost functional.

The only difference between RRT* and RA-RRT* here is the functional applied to
the per-segment cost distribution: the expectation for the risk-neutral planner,
CVaR_alpha for the risk-averse one.  Everything else -- sampling, steering,
collision checking, the near radius, ChooseParent, Rewire -- is shared, so a
difference in the paths is a difference in the risk functional and nothing else.
"""

import time

import numpy as np

from rarrt.risk import conditional_value_at_risk


class CostModel:
    """Cost of traversing a segment of length L at clearance d.

        cost = L * max(0, 1 + sigma * (Z + kappa * E * 1{U < p(d)})),
        p(d) = p_max * exp(-d / d_hazard),  Z ~ N(0,1), E ~ Exp(1), U ~ U(0,1).

    The Gaussian part is the ordinary traversal noise the paper models.  The
    exponential part is a hazard -- a slip, a snag, a re-plan -- whose chance
    rises as the segment passes closer to clutter, so clearance controls the
    tail and not just the mean.  The paper's own noise is exogenous (see the
    README); obstacle-coupled noise is what the manuscript's figure claim needs.

    The hazard is deliberately rare and severe (p_max = 0.15, kappa = 20) rather
    than frequent and moderate.  A frequent hazard is a shift in the mean, which
    the risk-neutral planner already avoids, and then the risk level has almost
    nothing left to do.  A tail event is what CVaR is for.

    The same fixed draws (common random numbers) are reused for every segment in
    a planner run, which makes the edge cost a deterministic function of
    (length, clearance).  RRT* needs that: an edge re-costed during Rewire has
    to return the same number it returned during ChooseParent.

    Because the noise is multiplicative and CVaR is positively homogeneous, the
    edge cost factors as L * g(d) with g(d) = CVaR_alpha(multiplier at d).  The
    risk level therefore reweights the metric by clearance; it does not merely
    add a constant per segment.
    """

    def __init__(self, sigma, alpha, n_samples=256, kappa=20.0, d_hazard=2.0,
                 p_max=0.15, seed=0):
        self.sigma = float(sigma)
        self.alpha = alpha
        self.kappa = float(kappa)
        self.d_hazard = float(d_hazard)
        self.p_max = float(p_max)
        rng = np.random.default_rng(seed)
        self.z = rng.standard_normal(n_samples)
        self.u = rng.random(n_samples)
        self.e = rng.exponential(size=n_samples)

    def hazard_chance(self, clearance):
        return self.p_max * np.exp(-np.maximum(clearance, 0.0) / self.d_hazard)

    def multipliers(self, clearance):
        """Cost multiplier samples, shape (B, n_samples)."""
        p = self.hazard_chance(np.atleast_1d(clearance))[:, None]
        hazard = (self.u[None, :] < p) * (self.kappa * self.e[None, :])
        return np.maximum(1.0 + self.sigma * (self.z[None, :] + hazard), 0.0)

    def edge_cost(self, length, clearance):
        if self.alpha is None:
            return np.asarray(length, dtype=float)
        g = conditional_value_at_risk(self.multipliers(clearance), self.alpha, axis=-1)
        return np.asarray(length, dtype=float) * g


def _near_radius(world, n, step, gamma_scale=1.5):
    """Karaman-Frazzoli radius in the plane, capped at twice the step."""
    area = (2.0 * world.half_width) ** 2
    gamma = 2.0 * np.sqrt(gamma_scale * area / np.pi)
    return min(gamma * np.sqrt(np.log(n + 1.0) / (n + 1.0)), 2.0 * step)


def plan(world, cost, iterations=1500, step=3.0, goal_bias=0.05, seed=0, keep_tree=False,
         on_iteration=None):
    """Grow an RRT* under `cost` and return the best path to the goal.

    Returns a dict with the path (or None), the cost-to-come at the goal in the
    planner's own units, the node count and the wall-clock planning time.

    `on_iteration(i, n, pts, parent, cost_to)`, when given, is called before
    iteration i and once more after the last one (i = iterations) with the live
    tree buffers; only the first n rows are in use.  It must not modify them.
    The planner draws nothing for it, so a recorded run grows the same tree.
    """
    rng = np.random.default_rng(seed)
    started = time.perf_counter()

    capacity = iterations + 1
    pts = np.empty((capacity, 2))
    parent = np.full(capacity, -1, dtype=np.int64)
    cost_to = np.zeros(capacity)
    pts[0] = world.start
    n = 1

    half = world.half_width
    for it in range(iterations):
        if on_iteration is not None:
            on_iteration(it, n, pts, parent, cost_to)
        target = world.goal if rng.random() < goal_bias else rng.uniform(-half, half, size=2)

        delta = pts[:n] - target
        nearest = int(np.argmin(np.einsum("ij,ij->i", delta, delta)))
        toward = target - pts[nearest]
        span = float(np.hypot(toward[0], toward[1]))
        if span < 1e-9:
            continue
        new_pt = pts[nearest] + toward * (min(step, span) / span)

        radius = _near_radius(world, n, step)
        reach = np.linalg.norm(pts[:n] - new_pt, axis=1)
        near = np.nonzero(reach <= radius)[0]
        if nearest not in near:
            near = np.append(near, nearest)

        clearance = world.segment_clearance(pts[near], np.broadcast_to(new_pt, (near.size, 2)))
        free = clearance > 0.0
        if not free[near == nearest][0]:
            continue  # standard RRT*: the steering edge itself must be free

        lengths = reach[near]
        edge = cost.edge_cost(lengths, clearance)
        through_new = np.where(free, cost_to[near] + edge, np.inf)
        best = int(np.argmin(through_new))
        if not np.isfinite(through_new[best]):
            continue

        new = n
        pts[new] = new_pt
        parent[new] = near[best]
        cost_to[new] = through_new[best]
        n += 1

        # Rewire.  The segment is undirected, so its length and clearance -- and
        # therefore its cost -- are the ones already computed above.
        rewired = cost_to[new] + edge
        for slot in np.nonzero(free & (rewired < cost_to[near] - 1e-12))[0]:
            node = int(near[slot])
            if node == parent[new] or rewired[slot] >= cost_to[node] - 1e-12:
                continue
            shift = rewired[slot] - cost_to[node]
            parent[node] = new
            cost_to[node] = rewired[slot]
            # Push the change down the subtree.  No cycle can appear: edge costs
            # are strictly positive, so a descendant of `node` always has a
            # larger cost-to-come and can never pass the test above.
            frontier = np.array([node])
            for _ in range(n):
                children = np.nonzero(np.isin(parent[:n], frontier))[0]
                if children.size == 0:
                    break
                cost_to[children] += shift
                frontier = children

    if on_iteration is not None:
        on_iteration(iterations, n, pts, parent, cost_to)
    elapsed = time.perf_counter() - started

    to_goal = np.linalg.norm(pts[:n] - world.goal, axis=1)
    reachable = np.nonzero(to_goal <= 2.0 * step)[0]
    result = {"path": None, "cost": np.inf, "nodes": n, "plan_time": elapsed}
    if keep_tree:
        result["tree_points"] = pts[:n].copy()
        result["tree_parent"] = parent[:n].copy()
    if reachable.size == 0:
        return result

    clearance = world.segment_clearance(pts[reachable], np.broadcast_to(world.goal, (reachable.size, 2)))
    total = np.where(clearance > 0.0,
                     cost_to[reachable] + cost.edge_cost(to_goal[reachable], clearance),
                     np.inf)
    best = int(np.argmin(total))
    if not np.isfinite(total[best]):
        return result

    chain = [int(reachable[best])]
    while parent[chain[-1]] >= 0:
        chain.append(int(parent[chain[-1]]))
    result["path"] = np.vstack([pts[chain[::-1]], world.goal])
    result["cost"] = float(total[best])
    return result


def path_geometry(world, path):
    """Segment lengths and clearances of a path, shapes (S,) and (S,)."""
    a, b = path[:-1], path[1:]
    return np.linalg.norm(b - a, axis=1), world.segment_clearance(a, b)


def execute(cost, lengths, clearances, trials, rng):
    """Realised traversal cost of a fixed path under fresh noise.

    Returns the total cost per trial, shape (trials,), and whether that trial hit
    at least one hazard, shape (trials,).

    Fresh draws, independent of the common random numbers the planner used, so
    a planner cannot look good merely by having optimised against its own sample.
    """
    p = cost.hazard_chance(clearances)[None, :]
    shape = (trials, lengths.size)
    z = rng.standard_normal(shape)
    hazard = (rng.random(shape) < p) * (cost.kappa * rng.exponential(size=shape))
    multiplier = np.maximum(1.0 + cost.sigma * (z + hazard), 0.0)
    return (multiplier * lengths[None, :]).sum(axis=1), (hazard > 0.0).any(axis=1)
