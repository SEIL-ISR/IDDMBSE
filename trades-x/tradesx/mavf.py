"""Multi-Attribute Value Function ranking.

Ported from the MATLAB workbench (`MAVF` in sysml/iddmbse_v2/MBO_rosbag_evals.m,
identical copy in MBO_rosbag_statisticalMAVF_evals.m): each metric column is
min-max normalised into a single-attribute value function (SAVF) on [0, 1]
where 1 is best, then the SAVFs are combined by a weighted sum.

The MATLAB version returned only the argmax. These functions return the whole
ranking.
"""

import numpy as np


def _checked(metrics, weights, sense):
    x = np.asarray(metrics, dtype=float)
    if x.ndim != 2:
        raise ValueError("metrics must be a 2-D (n_designs, n_metrics) array")
    w = np.asarray(weights, dtype=float).reshape(-1)
    s = np.asarray(sense, dtype=float).reshape(-1)
    if w.size != x.shape[1] or s.size != x.shape[1]:
        raise ValueError("weights and sense must have one entry per metric column")
    if np.any(w < 0):
        raise ValueError("weights must be non-negative")
    if not np.isclose(w.sum(), 1.0):
        raise ValueError("weights must sum to 1, got " + str(w.sum()))
    if not np.all(np.isin(s, (-1.0, 1.0))):
        raise ValueError("sense entries must be +1 (maximise) or -1 (minimise)")
    return x, w, s


def savf(metrics, sense):
    """Min-max normalised single-attribute value functions, 1 = best.

    A metric column whose values are all equal carries no information; its SAVF
    is set to 1 for every design rather than left as 0/0.
    """
    x = np.asarray(metrics, dtype=float)
    s = np.asarray(sense, dtype=float).reshape(-1)
    if x.ndim != 2 or s.size != x.shape[1]:
        raise ValueError("sense must have one entry per metric column")
    lo = x.min(axis=0)
    hi = x.max(axis=0)
    span = hi - lo
    flat = span == 0
    safe = np.where(flat, 1.0, span)
    up = (x - lo) / safe
    down = (hi - x) / safe
    v = np.where(s > 0, up, down)
    return np.where(flat, 1.0, v)


def mavf(metrics, weights, sense):
    """Weighted-sum MAVF score per design, higher is better."""
    x, w, s = _checked(metrics, weights, sense)
    return savf(x, s) @ w


def rank(metrics, weights, sense):
    """Full ranking by MAVF score.

    Returns (order, scores): `order` holds design indices best first, `scores`
    holds the MAVF score of every design in its original row order.
    """
    scores = mavf(metrics, weights, sense)
    order = np.argsort(-scores, kind="stable")
    return order, scores
