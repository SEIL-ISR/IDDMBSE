"""Split conformal prediction for axis-aligned bounding boxes.

Nonconformity score. For a detected box d and the true box t (both
(x_min, y_min, x_max, y_max)) the score is the smallest uniform outward
inflation that makes the detection cover the truth:

    s(d, t) = max(d_xmin - t_xmin, d_ymin - t_ymin, t_xmax - d_xmax, t_ymax - d_ymax)

A negative score means the raw detection already covers the truth. Inflating d
by q on every edge gives a region that contains t exactly when s(d, t) <= q,
which is what makes the calibration below a valid conformal procedure.

Quantile. With n exchangeable calibration scores the (1 - alpha) conformal
quantile is the k-th smallest score with k = ceil((n + 1)(1 - alpha)). If
k > n the quantile is +inf: the calibration set is too small to certify that
level. This finite-sample correction is what gives the marginal guarantee
P(t in R_alpha(d)) >= 1 - alpha; see Angelopoulos and Bates (2023), Section 1.
"""

import numpy as np


def scores(det, truth):
    """Nonconformity scores. det, truth (..., 4) -> (...)."""
    edges = np.stack(
        [
            det[..., 0] - truth[..., 0],
            det[..., 1] - truth[..., 1],
            truth[..., 2] - det[..., 2],
            truth[..., 3] - det[..., 3],
        ],
        axis=-1,
    )
    return np.max(edges, axis=-1)


def quantile(cal_scores, alpha):
    """The (1 - alpha) conformal quantile of a 1-D array of calibration scores."""
    s = np.sort(np.asarray(cal_scores, dtype=float).ravel())
    n = s.size
    k = int(np.ceil((n + 1) * (1.0 - alpha)))
    if k > n:
        return np.inf
    return float(s[k - 1])


def inflate(boxes, q):
    """Grow every box outward by q. q is a scalar or broadcasts over boxes[..., 0]."""
    q = np.asarray(q)
    pad = np.stack([-q, -q, q, q], axis=-1)
    return boxes + pad


def coverage(det, truth, q):
    """Fraction of detections whose inflation by q covers the truth."""
    return float(np.mean(scores(det, truth) <= q))


def bootstrap_coverage(det, truth, q, groups, rng, n_boot=2000, level=0.9):
    """A cluster bootstrap interval for the coverage.

    Detections inside one episode are not independent of each other: consecutive
    frames see the same objects from nearby poses. Resampling whole episodes,
    rather than rows, gives an interval that does not pretend otherwise.
    Returns (lower, upper) at the given central level.
    """
    hit = (scores(det, truth) <= q).astype(float)
    key, index = np.unique(np.asarray(groups), return_inverse=True)
    per_group_hits = np.bincount(index, weights=hit, minlength=key.size)
    per_group_rows = np.bincount(index, minlength=key.size).astype(float)
    pick = rng.integers(0, key.size, size=(n_boot, key.size))
    cov = per_group_hits[pick].sum(axis=1) / per_group_rows[pick].sum(axis=1)
    tail = 0.5 * (1.0 - level)
    lo, hi = np.quantile(cov, [tail, 1.0 - tail])
    return float(lo), float(hi)
