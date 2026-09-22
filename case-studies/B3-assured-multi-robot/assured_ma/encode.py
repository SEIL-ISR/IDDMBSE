"""Big-M MILP encoding of linearised dynamics plus STL satisfaction.

The formulation follows the STL encoding of Raman et al. (2014): every node of a
formula gets a continuous variable z that the constraints bound from above by the
node's robustness, and disjunctive nodes (staying outside a polytope, separation,
F_[a,b]) get one binary per disjunct with a big-M relaxation and an
at-least-one-selected row.

The fragment in `specs.py` has no negation, so every z appears only in upper-bound
rows. That gives two usable properties and `Problem.rho_required` picks between
them. Left at None, the objective pushes the root z up, every z is tight at an
optimum, and the root z equals the robustness `robustness.py` computes on the
returned trajectory - `tests/test_encode.py` checks that equality. Set to a number,
the root z is bounded below by it and the objective becomes control effort; since
z <= rho always holds, that lower bound is a sound way to require the plan to hold
that margin.

Each big-M is computed per row and per step from the box the robot can be in at that
step, rather than taken from a global constant: for a row `z <= e + M (1 - y)` the
value used is `M = ub(z) - lb(e)`, with `lb(e)` the exact minimum of the expression
over that box and `ub(z)` the node's upper bound. Nothing here loops over time steps
or robots; the structural loops are over formula nodes and halfspace rows.
"""

from dataclasses import dataclass, field

import numpy as np
from scipy.sparse import coo_matrix

from .specs import Alw, And, Ev, InSet, Or, OutSet, Sep

INF = np.inf


@dataclass
class Problem:
    N: int
    dt: float
    v_max: float
    a_max: float
    ws_lo: np.ndarray
    ws_hi: np.ndarray
    starts: np.ndarray            # (R, 2)
    rho_cap: float = 1.0
    effort_weight: float = 1e-3
    rho_required: float = None    # None: maximise robustness. Set: require this
                                  # margin and minimise control effort instead.

    @property
    def R(self):
        return self.starts.shape[0]

    @property
    def T(self):
        return self.N + 1


class VarPool:
    def __init__(self):
        self.lb, self.ub, self.integral, self.n = [], [], [], 0

    def add(self, count, lb, ub, integral=False):
        idx = np.arange(self.n, self.n + count)
        self.n += count
        self.lb.append(np.broadcast_to(np.asarray(lb, float), (count,)).copy())
        self.ub.append(np.broadcast_to(np.asarray(ub, float), (count,)).copy())
        self.integral.append(np.full(count, bool(integral)))
        return idx

    def finish(self):
        return (np.concatenate(self.lb), np.concatenate(self.ub),
                np.concatenate(self.integral).astype(np.int8))


class Rows:
    def __init__(self):
        self.cols, self.vals, self.rid, self.lo, self.hi, self.n = [], [], [], [], [], 0

    def add(self, cols, vals, lo=-INF, hi=INF):
        cols = np.asarray(cols)
        if cols.ndim == 1:
            cols = cols[:, None]
        vals = np.broadcast_to(np.asarray(vals, float), cols.shape)
        k = cols.shape[-1]
        cols = np.ascontiguousarray(cols).reshape(-1, k)
        vals = np.ascontiguousarray(vals).reshape(-1, k)
        m = cols.shape[0]
        self.rid.append(np.repeat(np.arange(self.n, self.n + m), cols.shape[1]))
        self.cols.append(cols.ravel())
        self.vals.append(vals.ravel())
        self.lo.append(np.broadcast_to(np.asarray(lo, float), (m,)).copy())
        self.hi.append(np.broadcast_to(np.asarray(hi, float), (m,)).copy())
        self.n += m

    def finish(self, n_vars):
        A = coo_matrix((np.concatenate(self.vals),
                        (np.concatenate(self.rid), np.concatenate(self.cols))),
                       shape=(self.n, n_vars)).tocsc()
        return A, np.concatenate(self.lo), np.concatenate(self.hi)


# ------------------------------------------------------------------
# bounds on each node's robustness over the workspace box

def node_bounds(node, prob, cache):
    key = id(node)
    if key in cache:
        return cache[key]
    lo, hi = prob.ws_lo, prob.ws_hi
    if isinstance(node, InSet):
        val = (np.min(node.poly.b - node.poly.support(lo, hi)),
               np.min(node.poly.b - node.poly.infimum(lo, hi)))
    elif isinstance(node, OutSet):
        val = (np.max(node.poly.infimum(lo, hi) - node.poly.b),
               np.max(node.poly.support(lo, hi) - node.poly.b))
    elif isinstance(node, Sep):
        val = (-node.d, float(np.max(hi - lo)) - node.d)
    elif isinstance(node, (And, Or)):
        b = np.array([node_bounds(c, prob, cache) for c in node.children])
        val = (b[:, 0].min(), b[:, 1].min()) if isinstance(node, And) else (b[:, 0].max(), b[:, 1].max())
    else:
        val = node_bounds(node.child, prob, cache)
    val = (float(val[0]), float(min(val[1], prob.rho_cap)))
    cache[key] = val
    return val


def collect_need(node, need, table):
    """Largest number of leading time points any parent asks this node for."""
    key = id(node)
    table[key] = max(table.get(key, 0), need)
    if isinstance(node, (And, Or)):
        for c in node.children:
            collect_need(c, need, table)
    elif isinstance(node, (Ev, Alw)):
        collect_need(node.child, need + node.hi, table)


@dataclass
class Encoding:
    prob: Problem
    pool: VarPool
    rows: Rows
    ipos: np.ndarray
    ivel: np.ndarray
    iacc: np.ndarray
    ieff: np.ndarray
    roots: list
    A: object = None
    blo: np.ndarray = None
    bhi: np.ndarray = None
    c: np.ndarray = None
    vlb: np.ndarray = None
    vub: np.ndarray = None
    integrality: np.ndarray = None
    node_cols: dict = field(default_factory=dict)

    @property
    def n_binary(self):
        return int(self.integrality.sum())


def _emit(node, prob, ctx):
    """Allocate the node's z variables and its rows; return the z column indices."""
    pool, rows, need_of, bounds, done = ctx["pool"], ctx["rows"], ctx["need"], ctx["bounds"], ctx["done"]
    key = id(node)
    if key in done:
        return done[key]
    need = need_of[key]
    zlo, zhi = node_bounds(node, prob, bounds)
    z = pool.add(need, zlo, zhi)
    ip = ctx["ipos"]
    lo, hi = prob.ws_lo, prob.ws_hi

    if isinstance(node, InSet):
        A, b = node.poly.A, node.poly.b
        p = ip[node.robot, :need]                                  # (need, 2)
        cols = np.concatenate([np.broadcast_to(z[:, None, None], (need, A.shape[0], 1)),
                               np.broadcast_to(p[:, None, :], (need, A.shape[0], 2))], axis=2)
        vals = np.concatenate([np.ones((need, A.shape[0], 1)),
                               np.broadcast_to(A[None, :, :], (need, A.shape[0], 2))], axis=2)
        rows.add(cols, vals, hi=np.broadcast_to(b, (need, A.shape[0])).ravel())

    elif isinstance(node, OutSet):
        A, b = node.poly.A, node.poly.b
        m = A.shape[0]
        # one big-M per row AND per step, from the box the robot can be in at that
        # step rather than from the whole workspace
        inf = (np.maximum(A, 0.0) @ ctx["plo"][node.robot, :need].T
               + np.minimum(A, 0.0) @ ctx["phi"][node.robot, :need].T).T      # (need, m)
        M = zhi - (inf - b)
        y = pool.add(need * m, 0, 1, integral=True).reshape(need, m)
        p = ip[node.robot, :need]
        cols = np.concatenate([np.broadcast_to(z[:, None, None], (need, m, 1)),
                               np.broadcast_to(p[:, None, :], (need, m, 2)),
                               y[:, :, None]], axis=2)
        vals = np.concatenate([np.ones((need, m, 1)),
                               np.broadcast_to(-A[None, :, :], (need, m, 2)),
                               M[:, :, None]], axis=2)
        rows.add(cols, vals, hi=(M - b).ravel())
        rows.add(y, 1.0, lo=1.0)

    elif isinstance(node, Sep):
        # four disjuncts: +/- (x_a - x_b) >= d and +/- (y_a - y_b) >= d
        sign = np.array([1.0, -1.0, 1.0, -1.0])
        axis = np.array([0, 0, 1, 1])
        la, ha = ctx["plo"][node.a, :need][:, axis], ctx["phi"][node.a, :need][:, axis]
        lb, hb = ctx["plo"][node.b, :need][:, axis], ctx["phi"][node.b, :need][:, axis]
        M = zhi - (np.where(sign > 0, la - hb, lb - ha) - node.d)  # (need, 4)
        y = pool.add(need * 4, 0, 1, integral=True).reshape(need, 4)
        pa = ip[node.a, :need][:, axis]                            # (need, 4)
        pb = ip[node.b, :need][:, axis]
        cols = np.stack([np.broadcast_to(z[:, None], (need, 4)), pa, pb, y], axis=2)
        vals = np.stack([np.ones((need, 4)),
                         np.broadcast_to(-sign, (need, 4)),
                         np.broadcast_to(sign, (need, 4)), M], axis=2)
        rows.add(cols, vals, hi=(M - node.d).ravel())
        rows.add(y, 1.0, lo=1.0)

    elif isinstance(node, And):
        for ch in node.children:
            zc = _emit(ch, prob, ctx)[:need]
            rows.add(np.stack([z, zc], axis=1), [1.0, -1.0], hi=0.0)

    elif isinstance(node, Or):
        k = len(node.children)
        y = pool.add(need * k, 0, 1, integral=True).reshape(need, k)
        for i, ch in enumerate(node.children):
            zc = _emit(ch, prob, ctx)[:need]
            M = zhi - node_bounds(ch, prob, bounds)[0]
            rows.add(np.stack([z, zc, y[:, i]], axis=1), [1.0, -1.0, M], hi=M)
        rows.add(y, 1.0, lo=1.0)

    elif isinstance(node, Alw):
        zc = _emit(node.child, prob, ctx)
        k = np.arange(node.lo, node.hi + 1)
        idx = zc[np.arange(need)[:, None] + k[None, :]]            # (need, width)
        cols = np.stack([np.broadcast_to(z[:, None], idx.shape), idx], axis=2)
        rows.add(cols, [1.0, -1.0], hi=0.0)

    elif isinstance(node, Ev):
        zc = _emit(node.child, prob, ctx)
        k = np.arange(node.lo, node.hi + 1)
        width = len(k)
        M = zhi - node_bounds(node.child, prob, bounds)[0]
        y = pool.add(need * width, 0, 1, integral=True).reshape(need, width)
        idx = zc[np.arange(need)[:, None] + k[None, :]]
        cols = np.stack([np.broadcast_to(z[:, None], idx.shape), idx, y], axis=2)
        vals = np.broadcast_to(np.array([1.0, -1.0, M]), cols.shape)
        rows.add(cols, vals, hi=M)
        rows.add(y, 1.0, lo=1.0)

    else:
        raise TypeError(node)

    done[key] = z
    return z


def build(prob, spec_by_robot):
    """Assemble the MILP. `spec_by_robot` is a list of one formula per robot."""
    R, N, T, dt = prob.R, prob.N, prob.T, prob.dt
    pool, rows = VarPool(), Rows()

    # Per-step boxes. The discrete update gives p_{k+1} - p_k = 0.5 dt (v_k + v_{k+1}),
    # so no coordinate can move more than v_max dt per step; the reachable box at step
    # k is the workspace intersected with start +/- v_max dt k. Likewise |v_k| cannot
    # exceed a_max dt k from rest. Both are exact, and both tighten the relaxation the
    # branch and bound search works from.
    k = np.arange(T)
    reach = prob.v_max * prob.dt * k
    plo = np.maximum(prob.ws_lo, prob.starts[:, None, :] - reach[None, :, None])
    phi = np.minimum(prob.ws_hi, prob.starts[:, None, :] + reach[None, :, None])
    vcap = np.minimum(prob.v_max, prob.a_max * prob.dt * k)

    ipos = pool.add(R * T * 2, plo.ravel(), phi.ravel()).reshape(R, T, 2)
    ivel = pool.add(R * T * 2, np.tile(-vcap.repeat(2), R), np.tile(vcap.repeat(2), R)).reshape(R, T, 2)
    iacc = pool.add(R * N * 2, -prob.a_max, prob.a_max).reshape(R, N, 2)
    ieff = pool.add(R * N * 2, 0.0, prob.a_max).reshape(R, N, 2)

    # double integrator, one block of rows for position and one for velocity
    rows.add(np.stack([ipos[:, 1:, :], ipos[:, :-1, :], ivel[:, :-1, :], iacc], axis=-1),
             [1.0, -1.0, -dt, -0.5 * dt * dt], lo=0.0, hi=0.0)
    rows.add(np.stack([ivel[:, 1:, :], ivel[:, :-1, :], iacc], axis=-1),
             [1.0, -1.0, -dt], lo=0.0, hi=0.0)

    # 1-norm epigraph on the acceleration
    rows.add(np.stack([ieff, iacc], axis=-1), [1.0, -1.0], lo=0.0)
    rows.add(np.stack([ieff, iacc], axis=-1), [1.0, 1.0], lo=0.0)

    need, bounds, done = {}, {}, {}
    for spec in spec_by_robot:
        collect_need(spec, 1, need)
    ctx = {"pool": pool, "rows": rows, "need": need, "bounds": bounds, "done": done,
           "ipos": ipos, "plo": plo, "phi": phi}
    roots = [int(_emit(spec, prob, ctx)[0]) for spec in spec_by_robot]

    vlb, vub, integrality = pool.finish()
    A, blo, bhi = rows.finish(pool.n)
    c = np.zeros(pool.n)
    if prob.rho_required is None:
        # maximise the robustness the plan holds, with a light penalty on effort
        c[roots] = -1.0
        c[ieff.ravel()] = prob.effort_weight
    else:
        # satisfaction with a required margin as a hard constraint, minimum
        # control effort as the objective
        vlb[roots] = prob.rho_required
        c[ieff.ravel()] = 1.0
    enc = Encoding(prob, pool, rows, ipos, ivel, iacc, ieff, roots,
                   A=A, blo=blo, bhi=bhi, c=c, vlb=vlb, vub=vub, integrality=integrality,
                   node_cols=done)
    return enc
