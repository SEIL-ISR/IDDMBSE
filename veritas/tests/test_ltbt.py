"""The ltbt MILP encoding. Skipped unless the `milp` extra is installed.

Without a Gurobi license beyond the size-limited one that ships with the pip package,
the solve is skipped too and only the import is checked.
"""

import numpy as np
import pytest

gp = pytest.importorskip("gurobipy", reason="install the milp extra: uv sync --extra milp")
pytest.importorskip("matplotlib", reason="ltbt.ternary imports matplotlib at module level")

from gurobipy import GRB

from ltbt.ternary import BoxConstraint, Constant, Eventually, Selector, Sequence, TRUE, FALSE, UNKNOWN


def test_three_valued_constants():
    assert (FALSE, UNKNOWN, TRUE) == (-1, 0, 1)


def test_small_double_integrator_solve():
    # the size-limited license that ships with pip gurobipy allows 200 variables for a
    # model with a quadratic objective; this encoding is 194 variables at n=5 and 253 at
    # n=6, and n=4 is infeasible for this specification
    n = 5
    dt = 1.0
    tol = 1e-6

    try:
        model = gp.Model("ltbt-test")
    except gp.GurobiError as err:
        pytest.skip("no usable Gurobi license: {}".format(err))

    model.Params.OutputFlag = 0
    model.Params.TimeLimit = 30

    X = model.addMVar(shape=(n, 4), lb=-GRB.INFINITY, ub=GRB.INFINITY, vtype=GRB.CONTINUOUS)
    U = model.addMVar(shape=(n - 1, 2), lb=-5, ub=5, vtype=GRB.CONTINUOUS)

    A = np.array([[1, dt, 0, 0], [0, 1, 0, 0], [0, 0, 1, dt], [0, 0, 0, 1]])
    B = np.array([[dt ** 2 / 2, 0], [dt, 0], [0, dt ** 2 / 2], [0, dt]])

    model.addConstr(X[1:] == X[:-1] @ A.T + U @ B.T)
    model.addConstr(X[0] == np.zeros(4))

    # one goal box around (1, 0), and a charger box the battery condition can select
    goal = BoxConstraint(model, X, [0.75, None, -0.25, None], [1.25, None, 0.25, None], None)
    charger = BoxConstraint(model, X, [-0.25, None, 0.75, None], [0.25, None, 1.25, None], None)

    batt = Constant(model, n, FALSE)
    phi = Sequence(model, Selector(model, batt, Eventually(model, charger, 0, n)),
                   Eventually(model, goal, 0, n))

    try:
        phi.enforce(model, 0, any=True)
        model.setObjective(sum(U[i] @ U[i] for i in range(n - 1)), GRB.MINIMIZE)
        model.optimize()
    except gp.GurobiError as err:
        pytest.skip("Gurobi refused the model (size-limited license?): {}".format(err))

    assert model.Status == GRB.OPTIMAL
    x = X.X
    # the battery condition is FALSE, so the selector has to fall through to the charger
    # box, and the sequence then has to reach the goal box: both must be visited
    xy = x[:, [0, 2]]
    in_charger = np.all((xy >= np.array([-0.25, 0.75]) - tol) & (xy <= np.array([0.25, 1.25]) + tol), axis=1)
    in_goal = np.all((xy >= np.array([0.75, -0.25]) - tol) & (xy <= np.array([1.25, 0.25]) + tol), axis=1)
    assert in_charger.any()
    assert in_goal.any()
    assert int(np.argmax(in_charger)) < int(np.argmax(in_goal))
