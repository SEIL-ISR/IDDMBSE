import numpy as np
import pytest

from cpnav import conformal, detector, planner, world


@pytest.fixture
def exact_detector(monkeypatch):
    """A detector that reports the truth, so planner tests stay deterministic."""
    monkeypatch.setattr(detector, "SIGMA0", 0.0)
    monkeypatch.setattr(detector, "SIGMA_RANGE", 0.0)
    monkeypatch.setattr(detector, "MU_EASY", 1.0)
    monkeypatch.setattr(detector, "SD_EASY", 0.0)
    monkeypatch.setattr(detector, "MU_HARD", 1.0)
    monkeypatch.setattr(detector, "SD_HARD", 0.0)
    monkeypatch.setattr(detector, "MAX_RANGE", 1e6)


@pytest.fixture
def blind_detector(monkeypatch):
    """A detector that reports nothing, so the planner drives on the prior."""
    monkeypatch.setattr(detector, "MAX_RANGE", 0.0)


def empty_world(n=1):
    return np.zeros((n, 1, 4)), np.zeros((n, 1), dtype=bool), np.zeros((n, 1), dtype=bool)


def test_cost_to_go_on_an_empty_grid_is_the_diagonal_distance():
    occ = np.zeros((1, world.NCELL, world.NCELL), dtype=bool)
    d = planner.cost_to_go(occ)
    r, c = world.START_RC
    gr, gc = world.GOAL_RC
    dr, dc = abs(gr - r), abs(gc - c)
    expect = (min(dr, dc) * np.sqrt(2.0) + abs(dr - dc)) * world.RES
    assert float(d[0, r, c]) == pytest.approx(expect, rel=1e-5)


def test_a_wall_makes_the_cost_to_go_infinite():
    occ = np.zeros((1, world.NCELL, world.NCELL), dtype=bool)
    occ[0, 18, :] = True
    d = planner.cost_to_go(occ)
    assert not np.isfinite(d[0, world.START_RC[0], world.START_RC[1]])


def test_planner_reaches_the_goal_on_an_empty_world():
    rng = np.random.default_rng(0)
    out = planner.run_episodes(rng, *empty_world(), q=0.0)
    assert out["status"][0] == planner.SUCCESS
    assert out["waits"][0] == 0
    gr, gc = world.GOAL_RC
    r, c = world.START_RC
    expect = min(abs(gr - r), abs(gc - c)) * np.sqrt(2.0) * world.RES
    assert out["length"][0] == pytest.approx(expect, rel=1e-6)


def test_conformal_inflation_never_shortens_the_path(exact_detector):
    # One obstacle beside the diagonal. A bigger q can only push the plan out.
    boxes = np.array([[[7.0, 8.0, 10.0, 11.0]]])
    valid = np.ones((1, 1), dtype=bool)
    hard = np.zeros((1, 1), dtype=bool)
    lengths = []
    for q in (0.0, 0.5, 1.0):
        rng = np.random.default_rng(0)
        out = planner.run_episodes(rng, boxes, valid, hard, q=q)
        assert out["status"][0] == planner.SUCCESS
        lengths.append(out["length"][0])
    assert lengths[0] <= lengths[1] <= lengths[2]


def test_a_wall_across_the_arena_stalls_the_robot(exact_detector):
    boxes = np.array([[[-10.0, 9.0, 30.0, 11.0]]])
    valid = np.ones((1, 1), dtype=bool)
    hard = np.zeros((1, 1), dtype=bool)
    rng = np.random.default_rng(0)
    out = planner.run_episodes(rng, boxes, valid, hard, q=0.0, max_steps=40)
    assert out["status"][0] == planner.STALLED
    assert out["waits"][0] > 0


def test_a_collision_is_flagged_when_the_path_crosses_a_true_box(blind_detector):
    # The detector reports nothing, so the planner drives the straight diagonal
    # and the swept step enters the true box sitting on it.
    boxes = np.array([[[8.0, 8.0, 12.0, 12.0]]])
    valid = np.ones((1, 1), dtype=bool)
    hard = np.zeros((1, 1), dtype=bool)
    rng = np.random.default_rng(0)
    out = planner.run_episodes(rng, boxes, valid, hard, q=0.0)
    assert out["status"][0] == planner.COLLISION

    # move the same box off the diagonal and the same run succeeds
    off = np.array([[[1.0, 14.0, 4.0, 17.0]]])
    rng = np.random.default_rng(0)
    clear = planner.run_episodes(rng, off, valid, hard, q=0.0)
    assert clear["status"][0] == planner.SUCCESS


def test_inside_any_matches_a_brute_force_oracle():
    rng = np.random.default_rng(5)
    lo = rng.uniform(0.0, 10.0, size=(4, 3, 2))
    boxes = np.concatenate([lo, lo + rng.uniform(0.2, 2.0, size=(4, 3, 2))], axis=2)
    valid = rng.random((4, 3)) < 0.7
    pts = rng.uniform(0.0, 12.0, size=(4, 6, 2))
    got = world.inside_any(boxes, valid, pts)

    # brute-force test oracle: explicit loops, used only to check the vectorised form
    want = np.zeros((4, 6), dtype=bool)
    for k in range(4):
        for p in range(6):
            for m in range(3):
                if not valid[k, m]:
                    continue
                x, y = pts[k, p]
                b = boxes[k, m]
                if b[0] <= x <= b[2] and b[1] <= y <= b[3]:
                    want[k, p] = True
    assert np.array_equal(got, want)


def test_the_footprint_grows_the_collision_region():
    boxes = np.array([[[4.0, 4.0, 6.0, 6.0]]])
    valid = np.ones((1, 1), dtype=bool)
    grown = conformal.inflate(boxes, world.ROBOT_HALF)
    pts = np.array([[[5.0, 5.0], [0.5, 0.5], [3.8, 5.0], [3.5, 5.0]]])
    assert np.array_equal(
        world.inside_any(grown, valid, pts), np.array([[True, False, True, False]])
    )
