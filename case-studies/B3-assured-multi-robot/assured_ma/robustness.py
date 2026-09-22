"""Quantitative STL robustness for the fragment in `specs.py`.

The recursion runs over the node structure of the formula, which is a handful of
nodes; every node evaluates its whole time signal in one array operation, so
nothing here loops over time steps or over robots.

Semantics are the standard discrete-time ones. A node whose formula reads `h`
steps into the future produces a signal of length `T - h`, i.e. only the times at
which its window is fully inside the trace. The certification value used by
VERITAS is the signal at time 0.
"""

import numpy as np
from numpy.lib.stride_tricks import sliding_window_view

from .specs import Alw, And, Ev, InSet, Or, OutSet, Sep


def _window(sig, lo, hi, reduce):
    width = hi - lo + 1
    if sig.shape[-1] - lo < width:
        raise ValueError("trace too short for interval [{}, {}]".format(lo, hi))
    return reduce(sliding_window_view(sig[..., lo:], width, axis=-1), axis=-1)


def evaluate(node, traj):
    """Robustness signal of `node` over `traj`, an array of shape (..., robots, T, 2).

    Any leading axes are batch axes carried through untouched, so a whole seed sweep
    is scored in one call. The returned signal has those same leading axes and a
    trailing time axis.
    """
    traj = np.asarray(traj, float)
    if isinstance(node, InSet):
        return (node.poly.b - traj[..., node.robot, :, :] @ node.poly.A.T).min(axis=-1)
    if isinstance(node, OutSet):
        return (traj[..., node.robot, :, :] @ node.poly.A.T - node.poly.b).max(axis=-1)
    if isinstance(node, Sep):
        return np.abs(traj[..., node.a, :, :] - traj[..., node.b, :, :]).max(axis=-1) - node.d
    if isinstance(node, (And, Or)):
        sigs = [evaluate(c, traj) for c in node.children]
        n = min(s.shape[-1] for s in sigs)
        stack = np.stack([s[..., :n] for s in sigs])
        return stack.min(axis=0) if isinstance(node, And) else stack.max(axis=0)
    if isinstance(node, Ev):
        return _window(evaluate(node.child, traj), node.lo, node.hi, np.max)
    if isinstance(node, Alw):
        return _window(evaluate(node.child, traj), node.lo, node.hi, np.min)
    raise TypeError(node)


def rho(node, traj):
    """Robustness at time 0: positive if and only if the trace satisfies the formula.

    With batch axes on `traj` this returns one value per batch element.
    """
    out = evaluate(node, traj)[..., 0]
    return float(out) if out.ndim == 0 else out


def explain(node, traj, t=0):
    """(rho at time t, a short text naming the leaf and step that attains it).

    Walks the one branch that carries the value, so the results table can say which
    conjunct a violation came from. Takes a single trajectory, no batch axes.
    """
    if isinstance(node, (InSet, OutSet, Sep)):
        return float(evaluate(node, traj)[t]), "{}@k={}".format(node.label or type(node).__name__, t)
    if isinstance(node, (And, Or)):
        vals = np.array([evaluate(c, traj)[t] for c in node.children])
        i = int(vals.argmin() if isinstance(node, And) else vals.argmax())
        return explain(node.children[i], traj, t)
    if isinstance(node, (Ev, Alw)):
        sig = evaluate(node.child, traj)
        w = sig[t + node.lo: t + node.hi + 1]
        k = int(w.argmax() if isinstance(node, Ev) else w.argmin())
        return explain(node.child, traj, t + node.lo + k)
    raise TypeError(node)


def resample(traj, factor):
    """Straight-line interpolation between waypoints, `factor` points per segment.

    The MILP constrains the trajectory at its sample times only, which is what
    discrete-time STL semantics mean. A straight segment between two clear samples
    can still clip an obstacle corner, so the case study checks the interpolated
    path as well.
    """
    traj = np.asarray(traj, float)
    s = np.linspace(0.0, 1.0, factor, endpoint=False)
    seg = (traj[..., :-1, :][..., None, :] * (1.0 - s)[:, None]
           + traj[..., 1:, :][..., None, :] * s[:, None])
    dense = seg.reshape(traj.shape[:-2] + (-1, 2))
    return np.concatenate([dense, traj[..., -1:, :]], axis=-2)


def dense_obstacle_margin(traj, obstacles, factor=20):
    """Smallest obstacle clearance along the interpolated path, over all robots."""
    dense = resample(traj, factor)
    vals = np.stack([(dense @ o.A.T - o.b).max(axis=-1) for o in obstacles])
    return float(vals.min())
