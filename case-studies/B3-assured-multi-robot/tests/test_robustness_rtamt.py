"""Cross-check the vectorised robustness against RTAMT.

RTAMT is an independent implementation of discrete-time STL robustness. Every
formula the case study uses is exported to an RTAMT specification string by
`specs.rtamt_expr` and evaluated on the same trace; the two numbers must agree.
"""

import numpy as np
import pytest
import rtamt

from assured_ma import robustness as rb
from assured_ma import specs

TOL = 1e-6


def rtamt_rho(node, traj):
    """Robustness at time 0 from RTAMT's StlDiscreteTimeSpecification."""
    traj = np.asarray(traj, float)
    R, T, _ = traj.shape
    spec = rtamt.StlDiscreteTimeSpecification()
    data = {"time": list(range(T))}
    for r in range(R):
        spec.declare_var("x{}".format(r), "float")
        spec.declare_var("y{}".format(r), "float")
        data["x{}".format(r)] = traj[r, :, 0].tolist()
        data["y{}".format(r)] = traj[r, :, 1].tolist()
    spec.spec = specs.rtamt_expr(node)
    spec.parse()
    return spec.evaluate(data)[0][1]


GOAL = specs.box((1.0, 2.0), (0.5, 1.5), "G")
OBS = specs.box((1.5, 2.5), (2.0, 3.0), "O")
TILTED = specs.Polytope([[1.0, 1.0], [-1.0, 1.0], [-1.0, -1.0], [1.0, -1.0]],
                        [6.0, -1.0, -3.0, 2.0], "P")

HAND = np.array([[[0.0, 0.5], [0.5, 0.7], [1.4, 1.0], [2.5, 1.2], [3.0, 2.4], [1.8, 2.6]]])


def formulas(R):
    out = [specs.Ev(1, 3, specs.InSet(0, GOAL, "G")),
           specs.Alw(0, 5, specs.OutSet(0, OBS, "O")),
           specs.Alw(0, 5, specs.OutSet(0, TILTED, "P")),
           specs.And((specs.Ev(1, 4, specs.InSet(0, GOAL, "G")),
                      specs.Alw(0, 5, specs.OutSet(0, OBS, "O")))),
           specs.Alw(1, 3, specs.Ev(0, 2, specs.InSet(0, GOAL, "G"))),
           specs.Or((specs.Ev(0, 2, specs.InSet(0, GOAL, "G")),
                     specs.Ev(3, 5, specs.InSet(0, GOAL, "G"))))]
    if R > 1:
        out.append(specs.Alw(0, 5, specs.Sep(0, 1, 0.8, "sep")))
        out.append(specs.And((specs.Ev(1, 3, specs.InSet(0, GOAL, "G")),
                              specs.Alw(0, 5, specs.And((specs.OutSet(0, OBS, "O"),
                                                         specs.Sep(0, 1, 0.8, "sep")))))))
    return out


@pytest.mark.parametrize("i", range(6))
def test_hand_built_trace(i):
    node = formulas(1)[i]
    assert abs(rb.rho(node, HAND) - rtamt_rho(node, HAND)) < TOL


@pytest.mark.parametrize("seed", [0, 1, 2, 3])
def test_random_traces_two_robots(seed):
    rng = np.random.default_rng(seed)
    traj = rng.uniform(0.0, 3.5, size=(2, 6, 2))
    for node in formulas(2):
        assert abs(rb.rho(node, traj) - rtamt_rho(node, traj)) < TOL, specs.rtamt_expr(node)


@pytest.mark.parametrize("seed", [0, 1])
def test_case_study_specs(seed):
    """The real phi_1 .. phi_3, on a synthetic trace, against RTAMT."""
    fleet = specs.load_fleet("model/fleet_requirements.yaml")
    T = fleet["N"] + 1
    rng = np.random.default_rng(seed)
    traj = np.cumsum(rng.normal(0.0, 0.35, size=(3, T, 2)), axis=1) + fleet["starts"][:, None, :]
    traj = np.clip(traj, [0.05, 0.05], [7.95, 5.95])
    for node in fleet["specs"]:
        assert abs(rb.rho(node, traj) - rtamt_rho(node, traj)) < TOL, node.label


def test_batched_matches_single():
    batch = np.stack([HAND, HAND + 0.2, HAND - 0.4])
    node = formulas(1)[3]
    one = np.array([rb.rho(node, b) for b in batch])
    assert np.allclose(rb.rho(node, batch), one, atol=1e-12)


def test_explain_names_the_binding_leaf():
    node = specs.Alw(0, 5, specs.OutSet(0, OBS, "O"))
    val, where = rb.explain(node, HAND)
    assert abs(val - rb.rho(node, HAND)) < 1e-12
    assert where.startswith("O@k=")
