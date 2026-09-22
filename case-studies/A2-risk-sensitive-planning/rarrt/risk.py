"""Risk measures on cost samples.

Cost convention: the variable is a cost, so the risk sits in the upper tail and
a larger confidence level alpha means more risk aversion.  This is the
convention of Enwerem et al. (2024), Eqs. (4a)-(5).
"""

import numpy as np
from scipy.optimize import minimize_scalar


def value_at_risk(x, alpha, axis=-1):
    """Empirical alpha-quantile of a cost sample.

    Uses the inverse-CDF (order statistic) convention, so the returned value is
    exactly the minimiser of the Rockafellar-Uryasev objective below.
    """
    x = np.asarray(x, dtype=float)
    if alpha <= 0.0:
        return x.min(axis=axis)
    return np.quantile(x, alpha, axis=axis, method="inverted_cdf")


def conditional_value_at_risk(x, alpha, axis=-1):
    """Empirical CVaR_alpha of a cost sample.

    CVaR_alpha(Y) = E[Y | Y >= VaR_alpha(Y)] = inf_z { z + E[Y-z]^+ / (1-alpha) }.
    The second form is evaluated at z = VaR_alpha, which is where the piecewise
    linear objective attains its minimum on the empirical distribution.

    alpha = 0 gives the sample mean (the risk-neutral end) and alpha = 1 the
    sample maximum.  Vectorised over every axis but `axis`.
    """
    x = np.asarray(x, dtype=float)
    if alpha <= 0.0:
        return x.mean(axis=axis)
    if alpha >= 1.0:
        return x.max(axis=axis)
    q = np.quantile(x, alpha, axis=axis, keepdims=True, method="inverted_cdf")
    excess = np.maximum(x - q, 0.0).mean(axis=axis, keepdims=True)
    return np.squeeze(q + excess / (1.0 - alpha), axis=axis)


def entropic_value_at_risk(x, alpha):
    """Empirical EVaR_alpha of a one-dimensional cost sample.

    EVaR_alpha(Y) = inf_{z>0} (1/z) log( E[exp(zY)] / (1-alpha) ).  EVaR is the
    tightest of the three on the Chernoff bound, so EVaR >= CVaR >= VaR.  The
    planner does not use it; it is here because the paper's risk vocabulary
    includes it and it is one line of scipy on top of the same samples.
    """
    x = np.asarray(x, dtype=float).ravel()
    if alpha <= 0.0:
        return float(x.mean())
    shift = x.max()
    log_one_minus = np.log1p(-alpha)

    def objective(u):
        z = np.exp(u)
        # log E[exp(zY)] computed around the sample maximum for stability
        return (np.log(np.mean(np.exp(z * (x - shift)))) + z * shift - log_one_minus) / z

    best = minimize_scalar(objective, bounds=(-14.0, 8.0), method="bounded")
    return float(objective(best.x))
