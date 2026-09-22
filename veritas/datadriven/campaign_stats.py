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
