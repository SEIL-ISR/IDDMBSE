"""Execution model: the synthesised plan is tracked, imperfectly.

A plan that satisfies its specification by construction cannot be what VERITAS
scores, or there would be nothing for the data-driven check to catch. What the
robots actually run is the plan under a first-order tracking-error process,

    e_0 = 0,   e_{k+1} = a e_k + w_k,   w_k ~ N(0, sigma^2) clipped at c sigma,
    executed_k = plan_k + e_k,

independently per axis and per robot. `a` is the closed-loop pole of a proportional
path follower and `sigma` the per-step disturbance; together they give a
steady-state error standard deviation of sigma / sqrt(1 - a^2). This is the
mechanism behind "what synthesis alone would miss": the plan holds its margin, the
execution spends some of it, and whether what is left is positive is a question only
the executed trace can answer.

The recursion is a convolution, so the whole rollout - every seed, every robot, every
axis - is one matrix product; nothing loops over time.
"""

import numpy as np


def error_process(shape, pole, sigma, clip_sigma, seed):
    """Tracking error of shape (draws, robots, T, 2), zero at k = 0."""
    draws, R, T, D = shape
    rng = np.random.default_rng(seed)
    w = np.clip(rng.normal(0.0, sigma, (draws, R, T - 1, D)), -clip_sigma * sigma, clip_sigma * sigma)
    k = np.arange(T - 1)
    L = np.where(k[:, None] >= k[None, :], pole ** np.abs(k[:, None] - k[None, :]), 0.0)
    e = np.zeros((draws, R, T, D))
    e[:, :, 1:, :] = np.einsum("ij,nrjd->nrid", L, w)
    return e


def execute(plan, pole, sigma, clip_sigma, seed, draws=1):
    """Executed trajectories of shape (draws, robots, T, 2).

    Draw 0 of any call with the same seed is the same trajectory whatever `draws` is,
    so the nominal run and the first element of a sweep agree.
    """
    plan = np.asarray(plan, float)
    e = error_process((draws,) + plan.shape, pole, sigma, clip_sigma, seed)
    return plan[None] + e
