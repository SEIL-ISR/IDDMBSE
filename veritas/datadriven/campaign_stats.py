"""Failure-rate and robustness statistics over a PERFECT simulation campaign.

This is the data-driven module of VERITAS (paper Sec. III-D (ii)): PERFECT runs a campaign
of trials, each trial either succeeds or fails, and optionally each trial carries an STL
robustness value computed post hoc over its recorded trajectory.  From those two arrays this
module produces the numbers an assurance argument can cite:

* a failure-rate point estimate and a (1 - delta) confidence interval, both the exact
  Clopper-Pearson one and the Wilson score one;
* the number of trials a campaign needs before its upper confidence bound on the failure
  rate reaches a target;
* summary statistics of the post-hoc robustness, with a distribution-free (DKW) correction
  on the empirical lower quantile.

Everything is whole-array numpy: `k` and `n` may be arrays and the bound functions broadcast.
"""

import numpy as np
from scipy import stats


# ------------------------------------------------------------------
# failure rate

def failure_rate(outcomes):
    """Point estimate of the failure probability.

    `outcomes` is a boolean array, True for a successful trial.  Returns (failures, trials,
    estimate); the estimate is nan for an empty campaign.
    """
    outcomes = np.asarray(outcomes, dtype=bool)
    n = outcomes.size
    k = int(np.count_nonzero(~outcomes))
    return k, n, (k / n if n else np.nan)


def clopper_pearson(k, n, delta=0.05):
    """Exact (conservative) two-sided 1 - delta interval for the failure probability.

    Inverts the binomial CDF through the Beta quantile function, so the coverage is at least
    1 - delta for every true p -- the bound to cite when the campaign is small.  k failures
    out of n trials; k and n broadcast.  The interval is clipped at 0 and 1, which is where
    the degenerate cases k = 0 and k = n land.
    """
    k = np.asarray(k, dtype=float)
    n = np.asarray(n, dtype=float)
    lo = np.where(k > 0, stats.beta.ppf(delta / 2, k, np.maximum(n - k + 1, 1e-12)), 0.0)
    hi = np.where(k < n, stats.beta.isf(delta / 2, k + 1, np.maximum(n - k, 1e-12)), 1.0)
    return np.nan_to_num(lo, nan=0.0), np.nan_to_num(hi, nan=1.0)


def clopper_pearson_upper(k, n, delta=0.05):
    """One-sided exact 1 - delta upper bound on the failure probability.

    This is the number a safety case wants: with confidence 1 - delta the true failure rate
    is no larger than this.  With k = 0 it reduces to 1 - delta**(1/n), the familiar
    zero-failure bound.
    """
    k = np.asarray(k, dtype=float)
    n = np.asarray(n, dtype=float)
    hi = np.where(k < n, stats.beta.isf(delta, k + 1, np.maximum(n - k, 1e-12)), 1.0)
    return np.nan_to_num(hi, nan=1.0)


def wilson(k, n, delta=0.05):
    """Wilson score 1 - delta interval for the failure probability.

    The normal-approximation interval with the continuity of the score statistic kept, so it
    stays inside [0, 1] and behaves at k = 0 and k = n where the Wald interval collapses.
    Narrower than Clopper-Pearson, and only asymptotically covering.
    """
    k = np.asarray(k, dtype=float)
    n = np.asarray(n, dtype=float)
    z = stats.norm.isf(delta / 2)
    p = k / n
    d = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / d
    half = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return np.clip(centre - half, 0.0, 1.0), np.clip(centre + half, 0.0, 1.0)


def trials_for_upper_bound(target, delta=0.05, failures=0, n_max=1_000_000):
    """Smallest campaign size whose exact upper bound on the failure rate reaches `target`.

    The sample-size design behind "run the campaign until the bound is tight enough": assume
    the campaign will see `failures` failures, and return the smallest n for which
    `clopper_pearson_upper(failures, n, delta) <= target`.  Returns -1 if n_max is not enough.

    Search is a vectorised scan over a geometric ladder followed by one over the bracketing
    decade -- no per-candidate loop.
    """
    if failures == 0:
        # closed form: 1 - delta**(1/n) <= target
        n = int(np.ceil(np.log(delta) / np.log1p(-target)))
        return n if n <= n_max else -1
    ladder = np.unique(np.geomspace(failures + 1, n_max, 200).astype(np.int64))
    ok = clopper_pearson_upper(failures, ladder, delta) <= target
    if not ok.any():
        return -1
    j = int(np.argmax(ok))
    lo = ladder[j - 1] + 1 if j else failures + 1
    grid = np.arange(lo, ladder[j] + 1)
    return int(grid[np.argmax(clopper_pearson_upper(failures, grid, delta) <= target)])


def trials_for_upper_bound_array(target, delta=0.05, failures=0, n_max=1_000_000):
    """`trials_for_upper_bound` for a whole column of failure counts at once.

    Same definition -- the smallest n with `clopper_pearson_upper(k, n, delta) <= target`, or
    -1 when n_max is not enough -- evaluated for every k in `failures` with two array passes:
    a shared geometric ladder to bracket each answer, then one grid over the brackets.
    """
    k = np.atleast_1d(np.asarray(failures, dtype=np.int64))
    ladder = np.unique(np.geomspace(1, n_max, 2000).astype(np.int64))
    ok = clopper_pearson_upper(k[:, None], ladder[None, :], delta) <= target
    found = ok.any(axis=1)
    j = ok.argmax(axis=1)
    lo = np.where(j > 0, ladder[np.maximum(j - 1, 0)] + 1, 1)
    hi = ladder[j]
    grid = lo[:, None] + np.arange(int((hi - lo).max()) + 1)[None, :]
    good = (grid <= hi[:, None]) & (clopper_pearson_upper(k[:, None], grid, delta) <= target)
    first = grid[np.arange(k.size), good.argmax(axis=1)]
    return np.where(found & good.any(axis=1), first, -1)


# ------------------------------------------------------------------
# post-hoc robustness

def dkw_epsilon(n, delta=0.05):
    """Dvoretzky-Kiefer-Wolfowitz band half-width: sup|F_n - F| <= eps with prob >= 1 - delta."""
    return np.sqrt(np.log(2 / delta) / (2 * np.asarray(n, dtype=float)))


def robustness_stats(rho, level=0.05, delta=0.05):
    """Summarise the post-hoc STL robustness of a campaign.

    `rho` is one robustness value per trial (negative means the trajectory violated the
    specification).  Returns a dict with

      n, mean, min, max, violated   -- the empirical fraction of trials with rho < 0
      quantile                      -- the empirical `level` quantile of rho
      quantile_dkw                  -- the same quantile pulled down by the DKW band, so with
                                       confidence 1 - delta at most a `level` fraction of
                                       future trials fall below it (-inf when the campaign is
                                       too small for the band to say anything)
      violated_dkw                  -- DKW upper bound on the violation fraction
      n_for_level                   -- the campaign size at which the band becomes narrower
                                       than `level`, i.e. at which `quantile_dkw` stops being
                                       -inf

    Both `level` (the tail being bounded) and `delta` (the confidence) are explicit because
    they are different quantities; they default to the same 0.05.
    """
    rho = np.asarray(rho, dtype=float)
    n = rho.size
    eps = dkw_epsilon(n, delta)
    shifted = level - eps
    return {
        "n": n,
        "n_for_level": int(np.ceil(np.log(2 / delta) / (2 * level * level))),
        "mean": float(rho.mean()) if n else np.nan,
        "min": float(rho.min()) if n else np.nan,
        "max": float(rho.max()) if n else np.nan,
        "violated": float(np.count_nonzero(rho < 0) / n) if n else np.nan,
        "quantile": float(np.quantile(rho, level)) if n else np.nan,
        "quantile_dkw": float(np.quantile(rho, shifted)) if n and shifted > 0 else -np.inf,
        "violated_dkw": float(min(1.0, np.count_nonzero(rho < 0) / n + eps)) if n else np.nan,
    }


def robustness_stats_by_group(rho, group, n_groups, level=0.05, delta=0.05):
    """`robustness_stats` for every group of a campaign at once.

    `group` is an integer group index per trial and `n_groups` how many there are, so this is
    the same summary as above evaluated per design and environment without splitting the
    campaign into per-group arrays.  Sorting once by (group, rho) puts every group's values in
    a contiguous, ordered block, which makes min, max and both quantiles plain indexing.
    Returns a dict of arrays of length `n_groups`; empty groups are nan.
    """
    rho = np.asarray(rho, dtype=float)
    g = np.asarray(group, dtype=np.int64)
    counts = np.bincount(g, minlength=n_groups)[:n_groups]
    nz = counts > 0
    if rho.size == 0:
        nan = np.full(n_groups, np.nan)
        return {"n": counts, "mean": nan, "min": nan, "max": nan, "violated": nan,
                "quantile": nan, "quantile_dkw": nan, "violated_dkw": nan}

    rs = rho[np.lexsort((rho, g))]
    starts = np.concatenate([[0], np.cumsum(counts)[:-1]])
    last = starts + np.maximum(counts - 1, 0)
    safe_n = np.maximum(counts, 1)

    eps = dkw_epsilon(safe_n, delta)
    shifted = level - eps
    n_violated = np.bincount(g, weights=(rho < 0).astype(float), minlength=n_groups)[:n_groups]
    return {
        "n": counts,
        "mean": np.where(nz, np.bincount(g, weights=rho, minlength=n_groups)[:n_groups] / safe_n,
                         np.nan),
        "min": np.where(nz, rs[np.minimum(starts, rs.size - 1)], np.nan),
        "max": np.where(nz, rs[np.minimum(last, rs.size - 1)], np.nan),
        "violated": np.where(nz, n_violated / safe_n, np.nan),
        "quantile": np.where(nz, _grouped_quantile(rs, starts, counts, level), np.nan),
        "quantile_dkw": np.where(nz & (shifted > 0),
                                 _grouped_quantile(rs, starts, counts, np.maximum(shifted, 0.0)),
                                 -np.inf),
        "violated_dkw": np.where(nz, np.minimum(1.0, n_violated / safe_n + eps), np.nan),
    }


def _grouped_quantile(rs, starts, counts, level):
    """Linear-interpolation quantile inside each contiguous block of the sorted array `rs`."""
    counts = np.maximum(counts, 1)
    pos = np.clip(np.asarray(level, dtype=float), 0.0, 1.0) * (counts - 1)
    i = np.floor(pos).astype(np.int64)
    frac = pos - i
    lo = np.minimum(starts + np.minimum(i, counts - 1), rs.size - 1)
    hi = np.minimum(starts + np.minimum(i + 1, counts - 1), rs.size - 1)
    return rs[lo] + frac * (rs[hi] - rs[lo])


# ------------------------------------------------------------------
# the report a campaign hands the assurance argument

def campaign_report(outcomes, rho=None, delta=0.05, target=None):
    """Everything above, over one campaign, as a flat dict."""
    k, n, p = failure_rate(outcomes)
    cp_lo, cp_hi = clopper_pearson(k, n, delta)
    w_lo, w_hi = wilson(k, n, delta)
    out = {
        "trials": n,
        "failures": k,
        "failure_rate": p,
        "delta": delta,
        "clopper_pearson": (float(cp_lo), float(cp_hi)),
        "clopper_pearson_upper": float(clopper_pearson_upper(k, n, delta)),
        "wilson": (float(w_lo), float(w_hi)),
    }
    if target is not None:
        out["trials_for_target"] = trials_for_upper_bound(target, delta, failures=k)
        out["target"] = target
    if rho is not None:
        out["robustness"] = robustness_stats(rho, delta=delta)
    return out


def format_report(r):
    """One block of text per campaign, for the demos."""
    lines = [
        "trials " + str(r["trials"]) + ", failures " + str(r["failures"])
        + ", failure rate " + str(round(r["failure_rate"], 4)),
        "Clopper-Pearson " + str(round(1 - r["delta"], 3)) + " interval  ["
        + str(round(r["clopper_pearson"][0], 4)) + ", " + str(round(r["clopper_pearson"][1], 4)) + "]",
        "Wilson " + str(round(1 - r["delta"], 3)) + " interval           ["
        + str(round(r["wilson"][0], 4)) + ", " + str(round(r["wilson"][1], 4)) + "]",
        "one-sided exact upper bound       " + str(round(r["clopper_pearson_upper"], 4)),
    ]
    if "target" in r:
        lines.append("trials needed for upper bound " + str(r["target"]) + " at this failure count: "
                     + str(r["trials_for_target"]))
    if "robustness" in r:
        s = r["robustness"]
        lines.append("robustness: mean " + str(round(s["mean"], 4)) + ", min " + str(round(s["min"], 4))
                     + ", violated " + str(round(s["violated"], 4)))
        dkw = ("-inf (the DKW band is wider than the quantile level; it takes "
               + str(s["n_for_level"]) + " trials)"
               if s["quantile_dkw"] == -np.inf else str(round(s["quantile_dkw"], 4)))
        lines.append("robustness quantile " + str(round(s["quantile"], 4))
                     + ", DKW-corrected " + dkw)
        lines.append("violation-fraction upper bound " + str(round(s["violated_dkw"], 4)))
    return "\n".join(lines)
