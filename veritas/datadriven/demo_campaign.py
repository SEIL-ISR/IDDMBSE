"""Failure-rate and robustness bounds over two campaigns.

First PERFECT's shipped dummy example, which has exactly one trial -- the bounds it gives are
degenerate and are printed to show what a one-trial campaign is worth.  Then a seeded
synthetic campaign of 200 trials with a known true failure probability, where the bounds can
be checked against the truth.
"""

import os
import sys

import numpy as np
from scipy import stats

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from campaign_stats import campaign_report, format_report  # noqa: E402
from perfect_adapter import read_campaign  # noqa: E402

repo = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
dummy_db = os.path.join(repo, "perfect", "examples", "dummy", "dummy.db")

# ------------------------------------------------------------------
# PERFECT's dummy example

c = read_campaign(dummy_db)
print("PERFECT dummy example: " + dummy_db)
print("designs " + str(sorted(set(c["design_name"]))) + ", states " + str(list(c["state"])))
print("wall-clock start_age " + str(np.round(c["start_age"], 3).tolist())
      + " s, sim_time " + str(c["sim_time"].tolist()))
print(format_report(campaign_report(c["success"], delta=0.05, target=0.05)))
print("one trial, zero failures: the point estimate is 0 and the exact upper bound is")
print("1 - 0.05**(1/1) = 0.95, i.e. this campaign rules out almost nothing. The line above")
print("says how many trials a zero-failure campaign needs before the bound reaches 0.05.")

# ------------------------------------------------------------------
# a synthetic campaign with a known truth

# each trial draws an STL robustness from N(0.15, 0.12) and fails exactly when it is negative,
# so the true failure probability is Phi(-0.15 / 0.12)
mu, sigma, n = 0.15, 0.12, 200
p_true = float(stats.norm.cdf(-mu / sigma))
rng = np.random.default_rng(20260922)
rho = rng.normal(mu, sigma, n)
success = rho >= 0

print()
print("synthetic campaign: " + str(n) + " trials, robustness ~ N(" + str(mu) + ", " + str(sigma)
      + "), failure iff robustness < 0")
print("true failure probability " + str(round(p_true, 5)))
print(format_report(campaign_report(success, rho=rho, delta=0.05, target=0.05)))
lo, hi = campaign_report(success, delta=0.05)["clopper_pearson"]
print("true rate inside the Clopper-Pearson interval: " + str(bool(lo <= p_true <= hi)))

# the same campaign ten times over, where the DKW band is finally narrower than the 5% level
rho = rng.normal(mu, sigma, 10 * n)
print()
print("the same campaign at " + str(10 * n) + " trials")
print(format_report(campaign_report(rho >= 0, rho=rho, delta=0.05, target=0.05)))
