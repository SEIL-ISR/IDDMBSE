"""Pareto (non-dominated) filtering over a design-by-metric table.

The model-based optimization stage of TRADES-X evaluates every candidate design
with first-principles oracles and keeps the non-dominated ones. Both filters
here are fully vectorised over designs: the dominance relation is built as an
(n_designs, n_designs) boolean matrix by numpy broadcasting.

Memory note: the comparison materialises an
(n_designs, n_designs, n_metrics) boolean array. At 4095 designs and 4 metrics
that is about 67 MB per comparison, which is what the sensor-suite case study
needs. For much larger design spaces, filter in blocks.
"""

import numpy as np


def _as_maximisation(metrics, sense):
    x = np.asarray(metrics, dtype=float)
    if x.ndim != 2:
        raise ValueError("metrics must be a 2-D (n_designs, n_metrics) array")
    n_metrics = x.shape[1]
    if sense is None:
        s = -np.ones(n_metrics)
    else:
        s = np.asarray(sense, dtype=float).reshape(-1)
        if s.size != n_metrics:
            raise ValueError("sense must have one entry per metric column")
        if not np.all(np.isin(s, (-1.0, 1.0))):
            raise ValueError("sense entries must be +1 (maximise) or -1 (minimise)")
    return x * s


def non_dominated(metrics, sense=None):
    """Standard Pareto filter.

    metrics: (n_designs, n_metrics) array.
    sense:   per-metric +1 to maximise, -1 to minimise. Default: minimise all.

    A design j is dominated when some other design i is at least as good on
    every metric and strictly better on at least one. Returns (mask, indices)
    with 0-based indices of the non-dominated designs, in increasing order.
    """
    x = _as_maximisation(metrics, sense)
    ge = (x[:, None, :] >= x[None, :, :]).all(axis=2)
    gt = (x[:, None, :] > x[None, :, :]).any(axis=2)
    dominates = ge & gt
    mask = ~dominates.any(axis=0)
    return mask, np.flatnonzero(mask)


def non_dominated_matlab_compat(metrics, sense=None):
    """The filter the MATLAB workbench used (`prtp` in sysml/iddmbse_v2/pareto.m).

    `prtp` keeps design k when, for every other design i, k is strictly better
    than i on at least one metric. That drops a design as soon as any other
    design is weakly better on every metric, with no strictness requirement, so
    exact duplicates and weakly dominated ties are removed. It is not the
    standard non-dominance test; its result is always a subset of
    `non_dominated`. Kept here so recorded MATLAB runs can be reproduced.
    """
    x = _as_maximisation(metrics, sense)
    weakly_better = (x[:, None, :] >= x[None, :, :]).all(axis=2)
    np.fill_diagonal(weakly_better, False)
    mask = ~weakly_better.any(axis=0)
    return mask, np.flatnonzero(mask)
