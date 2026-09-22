"""The MILP encoding: feasibility, obstacle routing, and the tightness of z.

The encoding is only worth anything if the robustness the solver reports is the
robustness the returned trajectory actually has. Every test here recomputes it with
`robustness.py` and compares. The last test adds a brute-force oracle over a coarse
grid of input sequences: whatever that grid can achieve, the MILP must match or beat.
"""

import numpy as np
import pytest

from assured_ma import robustness as rb
from assured_ma import specs, synth

GOAL = specs.box((2.5, 3.5), (2.5, 3.5), "G")
GAP_WALL = specs.box((1.5, 2.5), (0.0, 2.6), "W")     # leaves a gap above y = 2.6
FULL_WALL = specs.box((1.5, 2.5), (0.0, 4.0), "W")    # spans the workspace


def solve(prob, spec):
    out = synth.synthesise(prob, [spec], mip_rel_gap=0.0, time_limit=120.0)
    assert out["status"] == 0, out["message"]
    return out


def test_reaches_the_goal_inside_the_window(small_problem):
    prob = small_problem([0.5, 0.5])
    spec = specs.Ev(4, 8, specs.InSet(0, GOAL, "G"))
    out = solve(prob, spec)
    plan = out["plan"]
    inside = rb.evaluate(specs.InSet(0, GOAL, "G"), plan)[4:9]
    assert inside.max() > 0.0
    assert rb.rho(spec, plan) == pytest.approx(0.5, abs=1e-6)


def test_z_is_tight_on_the_returned_trajectory(small_problem):
    prob = small_problem([0.5, 0.5])
    spec = specs.And((specs.Ev(4, 8, specs.InSet(0, GOAL, "G")),
                      specs.Alw(0, 8, specs.OutSet(0, GAP_WALL, "W"))))
    out = solve(prob, spec)
    assert out["z_root"][0] == pytest.approx(rb.rho(spec, out["plan"]), abs=1e-6)


def test_solver_routes_around_the_obstacle(small_problem):
    prob = small_problem([0.5, 0.5])
    spec = specs.And((specs.Ev(4, 8, specs.InSet(0, GOAL, "G")),
                      specs.Alw(0, 8, specs.OutSet(0, GAP_WALL, "W"))))
    out = solve(prob, spec)
    plan = out["plan"]
    assert rb.rho(spec, plan) > 0.0
    outside = rb.evaluate(specs.OutSet(0, GAP_WALL, "W"), plan)
    assert outside.min() > 0.0, "a planned waypoint is inside the obstacle"
    assert out["z_root"][0] == pytest.approx(rb.rho(spec, plan), abs=1e-6)


def test_blocked_goal_gives_negative_robustness(small_problem):
    """With a wall across the whole workspace no trajectory satisfies the formula,
    so the optimum of the robustness-maximising MILP must be negative."""
    prob = small_problem([0.5, 0.5])
    spec = specs.And((specs.Ev(4, 8, specs.InSet(0, GOAL, "G")),
                      specs.Alw(0, 8, specs.OutSet(0, FULL_WALL, "W"))))
    out = solve(prob, spec)
    assert rb.rho(spec, out["plan"]) < 0.0
    assert out["z_root"][0] == pytest.approx(rb.rho(spec, out["plan"]), abs=1e-6)


def test_two_robots_keep_their_separation(small_problem):
    prob = small_problem([[0.4, 2.0], [0.4, 0.4]], N=6, ws=(3.0, 3.0))
    sep = specs.Sep(0, 1, 0.7, "sep")
    g0 = specs.box((2.0, 2.8), (0.2, 1.0), "G0")
    g1 = specs.box((2.0, 2.8), (2.0, 2.8), "G1")
    phi = [specs.And((specs.Ev(3, 6, specs.InSet(0, g0, "G0")), specs.Alw(0, 6, sep))),
           specs.And((specs.Ev(3, 6, specs.InSet(1, g1, "G1")), specs.Alw(0, 6, sep)))]
    out = synth.synthesise(prob, phi, mip_rel_gap=0.0, time_limit=180.0)
    assert out["status"] == 0, out["message"]
    plan = out["plan"]
    assert rb.evaluate(sep, plan).min() > 0.0
    for i, s in enumerate(phi):
        assert out["z_root"][i] == pytest.approx(rb.rho(s, plan), abs=1e-6)


def test_matches_a_brute_force_grid_oracle(small_problem):
    """Brute-force oracle: enumerate a coarse grid of acceleration sequences, keep the
    dynamically admissible ones, and score them. The MILP optimum cannot be worse."""
    prob = small_problem([0.2, 0.2], N=3, dt=0.5, v_max=1.0, a_max=1.0, ws=(3.0, 3.0))
    goal = specs.box((1.0, 2.0), (1.0, 2.0), "G")
    obs = specs.box((0.8, 1.2), (0.0, 0.8), "O")
    spec = specs.And((specs.Ev(1, 3, specs.InSet(0, goal, "G")),
                      specs.Alw(0, 3, specs.OutSet(0, obs, "O"))))
    out = solve(prob, spec)

    levels = np.array([-1.0, -0.5, 0.0, 0.5, 1.0])
    a = np.stack(np.meshgrid(*([levels] * 6), indexing="ij"), axis=-1).reshape(-1, 3, 2)
    k, j = np.arange(4), np.arange(3)
    W = np.where(k[:, None] > j[None, :], k[:, None] - j[None, :] - 0.5, 0.0)
    p = prob.starts[0] + prob.dt ** 2 * (W @ a)
    v = prob.dt * np.concatenate([np.zeros((len(a), 1, 2)), np.cumsum(a, axis=1)], axis=1)
    ok = ((np.abs(v) <= prob.v_max + 1e-9).all(axis=(1, 2))
          & (p >= prob.ws_lo - 1e-9).all(axis=(1, 2))
          & (p <= prob.ws_hi + 1e-9).all(axis=(1, 2)))
    best = rb.rho(spec, p[ok][:, None, :, :]).max()

    assert out["z_root"][0] == pytest.approx(rb.rho(spec, out["plan"]), abs=1e-6)
    assert rb.rho(spec, out["plan"]) >= best - 1e-6
