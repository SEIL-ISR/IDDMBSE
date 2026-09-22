import numpy as np
import pytest

from rarrt.world import World, make_world, free_fraction


def unit_disc_world():
    return World(half_width=10.0, centers=[[0.0, 0.0]], radii=[1.0],
                 start=[-8.0, -8.0], goal=[8.0, 8.0])


def test_a_segment_through_a_disc_is_in_collision():
    world = unit_disc_world()
    clearance = world.segment_clearance([[-2.0, 0.0]], [[2.0, 0.0]])
    assert clearance[0] == pytest.approx(-1.0)
    assert not world.collision_free([[-2.0, 0.0]], [[2.0, 0.0]])[0]


def test_a_segment_passing_above_a_disc_is_free_with_the_exact_clearance():
    world = unit_disc_world()
    clearance = world.segment_clearance([[-2.0, 2.0]], [[2.0, 2.0]])
    assert clearance[0] == pytest.approx(1.0)


def test_clearance_uses_the_closest_point_of_the_segment_not_the_endpoints():
    world = unit_disc_world()
    # the segment's endpoints are 5 away, its midpoint 3 away
    clearance = world.segment_clearance([[-4.0, 3.0]], [[4.0, 3.0]])
    assert clearance[0] == pytest.approx(2.0)


def test_a_segment_leaving_the_domain_is_in_collision():
    world = unit_disc_world()
    assert world.segment_clearance([[0.0, 5.0]], [[0.0, 11.0]])[0] < 0.0


def test_clearance_is_batched():
    world = unit_disc_world()
    a = np.array([[-2.0, 0.0], [-2.0, 2.0], [-4.0, 3.0]])
    b = np.array([[2.0, 0.0], [2.0, 2.0], [4.0, 3.0]])
    assert np.allclose(world.segment_clearance(a, b), [-1.0, 1.0, 2.0])


def test_generated_worlds_keep_the_start_and_the_goal_clear():
    for coverage in [0.08, 0.16, 0.26]:
        for seed in range(5):
            world = make_world(coverage, seed=seed)
            gap = np.linalg.norm(world.centers - world.start, axis=1) - world.radii
            assert (gap > 0.0).all()
            gap = np.linalg.norm(world.centers - world.goal, axis=1) - world.radii
            assert (gap > 0.0).all()


def test_obstacle_count_rises_with_the_coverage_target():
    counts = [make_world(c, seed=3).n_obstacles for c in [0.08, 0.16, 0.26]]
    assert counts[0] < counts[1] < counts[2]


def test_free_fraction_of_an_empty_world_is_one():
    world = World(10.0, np.empty((0, 2)), np.empty(0), [-8.0, -8.0], [8.0, 8.0])
    assert free_fraction(world, resolution=64) == 1.0
