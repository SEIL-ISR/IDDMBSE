import numpy as np
import pytest

from rarrt.rrtstar import CostModel, plan, path_geometry, execute
from rarrt.world import World, make_world


def empty_world(half_width=20.0):
    return World(half_width, np.empty((0, 2)), np.empty(0), [-16.0, -16.0], [16.0, 16.0])


def test_rrtstar_finds_a_path_in_an_empty_world():
    world = empty_world()
    result = plan(world, CostModel(sigma=0.0, alpha=None), iterations=400, seed=0)
    assert result["path"] is not None
    assert np.allclose(result["path"][0], world.start)
    assert np.allclose(result["path"][-1], world.goal)


def test_the_path_cost_falls_towards_the_straight_line_with_more_iterations():
    world = empty_world()
    straight = float(np.linalg.norm(world.goal - world.start))
    costs = [plan(world, CostModel(sigma=0.0, alpha=None), iterations=n, seed=0)["cost"]
             for n in [200, 600, 1800]]
    assert costs[0] >= costs[1] >= costs[2] >= straight - 1e-9
    assert costs[2] < 1.02 * straight


def test_the_reported_cost_equals_the_cost_of_the_returned_path():
    # this is the check on the ChooseParent and Rewire bookkeeping: the
    # cost-to-come carried in the tree has to match the path actually returned
    world = make_world(0.16, seed=2)
    cost = CostModel(sigma=0.3, alpha=0.9, seed=5)
    result = plan(world, cost, iterations=900, seed=11)
    assert result["path"] is not None
    lengths, clearances = path_geometry(world, result["path"])
    assert cost.edge_cost(lengths, clearances).sum() == pytest.approx(result["cost"], rel=1e-6)


def test_every_segment_of_a_returned_path_is_collision_free():
    world = make_world(0.26, seed=4)
    result = plan(world, CostModel(sigma=0.1, alpha=0.5, seed=5), iterations=900, seed=3)
    assert result["path"] is not None
    _, clearances = path_geometry(world, result["path"])
    assert (clearances > 0.0).all()


def test_the_risk_functional_is_the_only_difference_between_the_planners():
    # same seed, same samples, same collision checks: the node set is identical
    # and only the parent structure can differ
    world = make_world(0.16, seed=1)
    counts = []
    for alpha in [None, 0.0, 0.9]:
        result = plan(world, CostModel(sigma=0.5, alpha=alpha, seed=7), iterations=600, seed=9)
        counts.append(result["nodes"])
    assert counts[0] == counts[1] == counts[2]


def test_the_edge_cost_is_deterministic_and_ordered_by_risk_level():
    clearance = np.array([0.0, 1.0, 3.0, 10.0])
    length = np.full(4, 2.5)
    values = {}
    for alpha in [0.0, 0.1, 0.5, 0.9]:
        cost = CostModel(sigma=0.5, alpha=alpha, seed=13)
        first = cost.edge_cost(length, clearance)
        assert np.array_equal(first, cost.edge_cost(length, clearance))
        values[alpha] = first
    for lower, higher in [(0.0, 0.1), (0.1, 0.5), (0.5, 0.9)]:
        assert (values[higher] >= values[lower] - 1e-12).all()


def test_the_edge_cost_falls_as_clearance_grows():
    clearance = np.array([0.0, 0.5, 1.0, 2.0, 4.0, 12.0])
    for seed in range(20):
        cost = CostModel(sigma=0.5, alpha=0.9, seed=seed)
        assert (np.diff(cost.edge_cost(np.ones(6), clearance)) <= 1e-12).all()


def test_the_common_random_numbers_estimate_the_true_cvar():
    # the planner reuses one fixed sample set for every segment in a run, so the
    # edge cost has to track the CVaR of the underlying distribution.  The
    # reference is two million fresh samples; the tolerance is on the average
    # over twenty planner seeds, which is what a campaign cell averages over.
    clearance = np.array([0.0, 0.5, 1.0, 2.0, 4.0, 8.0])
    reference = CostModel(sigma=0.5, alpha=0.9, n_samples=2_000_000,
                          seed=99).edge_cost(np.ones(6), clearance)
    estimates = np.array([CostModel(sigma=0.5, alpha=0.9, n_samples=2048,
                                    seed=seed).edge_cost(np.ones(6), clearance)
                          for seed in range(20)])
    assert np.abs(estimates.mean(axis=0) - reference).max() < 0.05 * reference.max()


def test_execution_costs_are_at_least_zero_and_average_above_the_nominal_length():
    world = make_world(0.16, seed=2)
    cost = CostModel(sigma=0.3, alpha=0.9, seed=5)
    result = plan(world, cost, iterations=900, seed=11)
    lengths, clearances = path_geometry(world, result["path"])
    realized, hazard = execute(cost, lengths, clearances, 5000, np.random.default_rng(0))
    assert realized.shape == (5000,) and hazard.shape == (5000,)
    assert (realized >= 0.0).all()
    assert realized.mean() > lengths.sum()
