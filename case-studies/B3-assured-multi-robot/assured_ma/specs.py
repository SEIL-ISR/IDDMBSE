"""The STL fragment used by case study B3.

Reach-avoid missions need very little of STL: halfspace predicates over a robot's
position, a pairwise separation predicate, conjunction and disjunction, and the two
bounded temporal operators F_[a,b] and G_[a,b]. That is the whole fragment.

The nodes below are plain dataclasses. `robustness.py` evaluates them over a
trajectory array and `encode.py` turns them into MILP rows. Both walk the same
tree, so the quantity the MILP maximises and the quantity VERITAS scores after
execution are the same by construction.

Time is in steps everywhere; interval bounds are inclusive. Halfspace rows are
normalised to unit length when a Polytope is built, so a predicate's robustness is
a signed distance in metres.
"""

from dataclasses import dataclass

import numpy as np
import yaml


class Polytope:
    """{x : A x <= b} in halfspace (H-) representation, rows normalised."""

    def __init__(self, A, b, name=""):
        A = np.atleast_2d(np.asarray(A, float))
        b = np.asarray(b, float).reshape(-1)
        n = np.linalg.norm(A, axis=1)
        self.A = A / n[:, None]
        self.b = b / n
        self.name = name

    @property
    def m(self):
        return self.A.shape[0]

    def support(self, lo, hi):
        """max of A x over the box [lo, hi], one value per row."""
        return np.maximum(self.A, 0.0) @ hi + np.minimum(self.A, 0.0) @ lo

    def infimum(self, lo, hi):
        """min of A x over the box [lo, hi], one value per row."""
        return np.maximum(self.A, 0.0) @ lo + np.minimum(self.A, 0.0) @ hi

    def vertices(self):
        """Vertices of a bounded 2-D polytope, ordered counter-clockwise.

        Every pair of rows is intersected and the points that satisfy all rows are
        kept, then sorted by angle. Only used for plotting.
        """
        i, j = np.triu_indices(self.m, k=1)
        M = np.stack([self.A[i], self.A[j]], axis=1)
        rhs = np.stack([self.b[i], self.b[j]], axis=1)
        det = np.linalg.det(M)
        ok = np.abs(det) > 1e-9
        pts = np.linalg.solve(M[ok], rhs[ok][..., None])[..., 0]
        inside = np.all(pts @ self.A.T <= self.b + 1e-7, axis=1)
        pts = np.unique(np.round(pts[inside], 9), axis=0)
        c = pts.mean(axis=0)
        return pts[np.argsort(np.arctan2(pts[:, 1] - c[1], pts[:, 0] - c[0]))]


def box(xlim, ylim, name=""):
    A = np.array([[-1.0, 0.0], [1.0, 0.0], [0.0, -1.0], [0.0, 1.0]])
    b = np.array([-xlim[0], xlim[1], -ylim[0], ylim[1]], float)
    return Polytope(A, b, name)


# ------------------------------------------------------------------
# nodes

@dataclass(eq=False)
class InSet:
    """x_robot lies in the polytope. rho = min_j (b_j - a_j . x)."""
    robot: int
    poly: Polytope
    label: str = ""


@dataclass(eq=False)
class OutSet:
    """x_robot lies outside the polytope. rho = max_j (a_j . x - b_j)."""
    robot: int
    poly: Polytope
    label: str = ""


@dataclass(eq=False)
class Sep:
    """Infinity-norm separation. rho = ||x_a - x_b||_inf - d."""
    a: int
    b: int
    d: float
    label: str = ""


@dataclass(eq=False)
class And:
    children: tuple
    label: str = ""


@dataclass(eq=False)
class Or:
    children: tuple
    label: str = ""


@dataclass(eq=False)
class Ev:
    """F_[lo,hi] child."""
    lo: int
    hi: int
    child: object
    label: str = ""


@dataclass(eq=False)
class Alw:
    """G_[lo,hi] child."""
    lo: int
    hi: int
    child: object
    label: str = ""


LEAVES = (InSet, OutSet, Sep)


def horizon(node):
    """Number of future steps the node reads beyond the time it is evaluated at."""
    if isinstance(node, LEAVES):
        return 0
    if isinstance(node, (And, Or)):
        return max(horizon(c) for c in node.children)
    return node.hi + horizon(node.child)


def robots_of(node):
    if isinstance(node, (InSet, OutSet)):
        return {node.robot}
    if isinstance(node, Sep):
        return {node.a, node.b}
    if isinstance(node, (And, Or)):
        return set().union(*(robots_of(c) for c in node.children))
    return robots_of(node.child)


# ------------------------------------------------------------------
# export to an RTAMT specification string

def _lin(a, r):
    return "{}*x{} + {}*y{}".format(repr(float(a[0])), r, repr(float(a[1])), r)


def rtamt_expr(node):
    """The same formula as an RTAMT StlDiscreteTimeSpecification string.

    RTAMT's robustness for `e <= c` is c - e and for `e >= c` is e - c, and its
    `and`/`or` are min/max, so this string and `robustness.py` compute the same
    number on the same trace. Used by the cross-check test.
    """
    if isinstance(node, InSet):
        parts = ["({} <= {})".format(_lin(node.poly.A[j], node.robot), repr(float(node.poly.b[j])))
                 for j in range(node.poly.m)]
        return "(" + " and ".join(parts) + ")"
    if isinstance(node, OutSet):
        parts = ["({} >= {})".format(_lin(node.poly.A[j], node.robot), repr(float(node.poly.b[j])))
                 for j in range(node.poly.m)]
        return "(" + " or ".join(parts) + ")"
    if isinstance(node, Sep):
        d = repr(float(node.d))
        parts = ["(x{} - x{} >= {})".format(node.a, node.b, d),
                 "(x{} - x{} >= {})".format(node.b, node.a, d),
                 "(y{} - y{} >= {})".format(node.a, node.b, d),
                 "(y{} - y{} >= {})".format(node.b, node.a, d)]
        return "(" + " or ".join(parts) + ")"
    if isinstance(node, And):
        return "(" + " and ".join(rtamt_expr(c) for c in node.children) + ")"
    if isinstance(node, Or):
        return "(" + " or ".join(rtamt_expr(c) for c in node.children) + ")"
    if isinstance(node, Ev):
        return "(eventually[{}:{}]{})".format(node.lo, node.hi, rtamt_expr(node.child))
    if isinstance(node, Alw):
        return "(always[{}:{}]{})".format(node.lo, node.hi, rtamt_expr(node.child))
    raise TypeError(node)


def pretty(node):
    """The formula in ordinary STL notation, for the README and the printout."""
    if isinstance(node, (InSet, OutSet, Sep)):
        return node.label or type(node).__name__
    if isinstance(node, And):
        return "(" + " & ".join(pretty(c) for c in node.children) + ")"
    if isinstance(node, Or):
        return "(" + " | ".join(pretty(c) for c in node.children) + ")"
    if isinstance(node, Ev):
        return "F_[{},{}]{}".format(node.lo, node.hi, pretty(node.child))
    if isinstance(node, Alw):
        return "G_[{},{}]{}".format(node.lo, node.hi, pretty(node.child))
    raise TypeError(node)


# ------------------------------------------------------------------
# step 3 of the chain: parse the per-robot missions into reach-avoid STL

def _polytope(entry):
    if entry.get("type", "box") == "box":
        return box(entry["x"], entry["y"], entry["id"])
    return Polytope(entry["A"], entry["b"], entry["id"])


def load_fleet(path, allocation=None):
    """Read model/fleet_requirements.yaml and build phi_1 .. phi_R.

    `allocation` is an optional permutation: allocation[i] is the index of the goal
    pair given to robot i. The identity is the allocation written in the model file;
    other permutations are what the TRADES-X sweep explores.

    Each mission becomes

        phi_i = F_[a1,b1](x_i in Goal_i^1) & F_[a2,b2](x_i in Goal_i^2)
                & G_[0,N]( &_j (x_i not in Obs_j) & &_{j != i} (|x_i - x_j|_inf >= d) )
    """
    cfg = yaml.safe_load(open(path))
    N = cfg["horizon"]["steps"]
    obstacles = [_polytope(o) for o in cfg["obstacles"]]
    starts = np.array([r["start"] for r in cfg["robots"]], float)
    R = len(cfg["robots"])
    if allocation is None:
        allocation = list(range(R))
    goal_sets = [[( _polytope({**g, "type": "box"}), tuple(g["window"]) ) for g in r["goals"]]
                 for r in cfg["robots"]]

    d = cfg["separation"]["d_min"]
    sep = {}
    for i in range(R):
        for j in range(i + 1, R):
            sep[(i, j)] = Sep(i, j, d, "sep({},{})".format(i + 1, j + 1))

    out = []
    for i in range(R):
        reach = [Ev(w[0], w[1], InSet(i, g, g.name), "F" + g.name)
                 for g, w in goal_sets[allocation[i]]]
        avoid = [OutSet(i, o, o.name) for o in obstacles]
        keep = [sep[(min(i, j), max(i, j))] for j in range(R) if j != i]
        out.append(And(tuple(reach) + (Alw(0, N, And(tuple(avoid + keep))),),
                       "phi_{}".format(i + 1)))
    return {"cfg": cfg, "obstacles": obstacles, "starts": starts, "N": N,
            "goal_sets": [goal_sets[allocation[i]] for i in range(R)],
            "allocation": list(allocation), "specs": out}
