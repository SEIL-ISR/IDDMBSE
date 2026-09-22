"""The node limit on the branch-and-bound search.

The PERFECT campaign stops every solve after a fixed number of nodes rather than
after a fixed number of seconds, so that a trial's plan does not depend on how many
other trials share the machine. These tests hold `synth.synthesise` to that: the
limit is passed through, the search stops there, and two stopped searches return
the same incumbent.

The instance is two robots crossing a gap in a wall under the separation
predicate, small enough to solve in well under a second and still needing a few
dozen nodes to prove its optimum.
"""

import numpy as np
import pytest

from assured_ma import encode, specs, synth

WALL = specs.box((1.5, 2.5), (0.0, 2.6), "W")
G0 = specs.box((3.0, 3.8), (3.0, 3.8), "G0")
G1 = specs.box((3.0, 3.8), (0.2, 1.0), "G1")
SEP = specs.Sep(0, 1, 0.5, "sep")


def instance():
    prob = encode.Problem(N=8, dt=0.5, v_max=1.0, a_max=1.5, ws_lo=np.zeros(2),
                          ws_hi=np.array([4.0, 4.0]),
                          starts=np.array([[0.5, 0.5], [0.5, 3.5]]))
    phi = [specs.And((specs.Ev(5, 8, specs.InSet(i, g, g.name)),
                      specs.Alw(0, 8, specs.And((specs.OutSet(i, WALL, "W"), SEP)))))
           for i, g in enumerate((G0, G1))]
    return prob, phi


def test_the_unlimited_search_needs_more_than_a_handful_of_nodes():
    prob, phi = instance()
    out = synth.synthesise(prob, phi, mip_rel_gap=0.0, time_limit=60.0)
    assert out["status"] == 0
    assert out["nodes"] > 5
    assert out["mip_gap"] == pytest.approx(0.0, abs=1e-9)


def test_a_node_limit_stops_the_search_with_an_incumbent():
    prob, phi = instance()
    cut = synth.synthesise(prob, phi, mip_rel_gap=0.0, time_limit=60.0, node_limit=5)
    assert cut["status"] != 0
    assert "Solution limit" in cut["message"]
    assert cut["nodes"] <= 5
    assert "plan" in cut
    assert cut["mip_gap"] > 0.0
    assert cut["dual_bound"] is not None


def test_a_node_limited_search_returns_the_same_incumbent_twice():
    prob, phi = instance()
    a = synth.synthesise(prob, phi, mip_rel_gap=0.0, time_limit=60.0, node_limit=5)
    b = synth.synthesise(prob, phi, mip_rel_gap=0.0, time_limit=60.0, node_limit=5)
    assert np.array_equal(a["plan"], b["plan"])
    assert a["nodes"] == b["nodes"]
