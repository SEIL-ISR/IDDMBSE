"""The execution model, and what it does to robustness."""

import numpy as np
import pytest

from assured_ma import execute
from assured_ma import robustness as rb
from assured_ma import specs

OBS = specs.box((2.0, 3.0), (0.0, 2.0), "O")
PLAN = np.array([[[0.5, 2.6], [1.5, 2.6], [2.5, 2.6], [3.5, 2.6], [4.5, 2.6]]])
SPEC = specs.Alw(0, 4, specs.OutSet(0, OBS, "O"))


def test_zero_noise_reproduces_the_plan():
    out = execute.execute(PLAN, pole=0.8, sigma=0.0, clip_sigma=3.0, seed=7, draws=4)
    assert np.allclose(out, PLAN[None])


def test_first_draw_does_not_depend_on_how_many_are_drawn():
    one = execute.execute(PLAN, 0.8, 0.09, 3.0, seed=3, draws=1)
    many = execute.execute(PLAN, 0.8, 0.09, 3.0, seed=3, draws=20)
    assert np.allclose(one[0], many[0])


def test_error_starts_at_zero_and_stays_bounded():
    e = execute.error_process((6, 2, 21, 2), pole=0.8, sigma=0.09, clip_sigma=3.0, seed=1)
    assert np.allclose(e[:, :, 0, :], 0.0)
    assert np.abs(e).max() < 3.0 * 0.09 / (1.0 - 0.8) + 1e-9


def test_drift_toward_the_obstacle_costs_robustness():
    """The plan clears the obstacle by 0.6 m in y. Push the execution down by 0.25 m
    and exactly that much robustness is gone; push it up and none is."""
    planned = rb.rho(SPEC, PLAN)
    assert planned == pytest.approx(0.6, abs=1e-9)
    toward = PLAN - np.array([0.0, 0.25])
    away = PLAN + np.array([0.0, 0.25])
    assert rb.rho(SPEC, toward) == pytest.approx(planned - 0.25, abs=1e-9)
    assert rb.rho(SPEC, toward) < planned
    assert rb.rho(SPEC, away) > planned


def test_enough_drift_turns_a_satisfied_plan_into_a_violation():
    violated = PLAN - np.array([0.0, 0.75])
    assert rb.rho(SPEC, PLAN) > 0.0
    assert rb.rho(SPEC, violated) < 0.0


def test_noise_can_only_be_scored_on_the_executed_trace():
    """Over a sweep the executed robustness spreads around the planned value; the
    plan's own value says nothing about any individual run."""
    runs = execute.execute(PLAN, 0.8, 0.12, 3.0, seed=0, draws=64)
    scored = rb.rho(SPEC, runs)
    assert scored.shape == (64,)
    assert scored.min() < rb.rho(SPEC, PLAN) < scored.max()
