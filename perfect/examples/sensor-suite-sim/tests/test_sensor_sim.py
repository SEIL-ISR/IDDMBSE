"""The batched pieces of the simulation against brute-force oracles.

Every oracle here is a deliberately slow, obviously-correct loop written only to
check the whole-array version. The simulation itself never loops over draws,
rocks or sensors.
"""

import heapq

import numpy as np
import pytest

import sensor_sim as S


# ------------------------------------------------------------------
# cost-to-go against Dijkstra

def dijkstra_oracle(occ, goal_rc):
    """Brute-force test oracle: 8-connected Dijkstra with a priority queue."""
    h, w = occ.shape
    d = np.full((h, w), np.inf)
    if occ[goal_rc]:
        return d
    d[goal_rc] = 0.0
    queue = [(0.0, goal_rc)]
    while queue:
        cost, (r, c) = heapq.heappop(queue)
        if cost > d[r, c]:
            continue
        for (dr, dc), step in zip(S.NEIGHBOURS, S.STEP_COST):
            nr, nc = r + dr, c + dc
            if not (0 <= nr < h and 0 <= nc < w) or occ[nr, nc]:
                continue
            if cost + step < d[nr, nc]:
                d[nr, nc] = cost + step
                heapq.heappush(queue, (d[nr, nc], (nr, nc)))
    return d


@pytest.mark.parametrize("seed", range(6))
def test_cost_to_go_matches_dijkstra(seed):
    rng = np.random.default_rng(seed)
    occ = rng.random((4, 14, 14)) < 0.22
    occ[:, 13, 13] = False
    got = S.cost_to_go(occ, goal_rc=(13, 13))
    want = np.stack([dijkstra_oracle(o, (13, 13)) for o in occ])
    assert np.allclose(got, want, equal_nan=True, atol=1e-5)


def test_cost_to_go_blocks_a_wall():
    occ = np.zeros((1, 9, 9), dtype=bool)
    occ[0, :, 4] = True
    d = S.cost_to_go(occ, goal_rc=(0, 8))
    assert not np.isfinite(d[0, 0, 0])
    assert np.isfinite(d[0, 0, 7])


# ------------------------------------------------------------------
# detection probability against an explicit loop

def report_probability_oracle(dist, bearing, radius, rate, h_fov, ares, reach, gain, dt):
    """Brute-force test oracle: one Python loop per draw, rock and sensor."""
    k, m = dist.shape
    out = np.zeros((k, m))
    for i in range(k):
        for j in range(m):
            miss = 1.0
            for s in range(len(rate)):
                d = dist[i, j]
                if abs(bearing[i, j]) > 0.5 * h_fov[s] or d > reach[s]:
                    continue
                length = 2.0 * radius[j] / (S.SAMPLES_TO_RESOLVE * ares[s])
                p = np.exp(-d / length) * gain[s]
                looks = max(rate[s] * dt, 1.0) ** S.LOOK_EXPONENT
                miss *= (1.0 - p) ** looks
            out[i, j] = 1.0 - miss
    return out


def test_report_probability_matches_oracle():
    rng = np.random.default_rng(3)
    k, m, s = 5, 7, 4
    dist = rng.uniform(0.5, 40.0, size=(k, m))
    bearing = rng.uniform(-np.pi, np.pi, size=(k, m))
    radius = rng.uniform(0.6, 1.8, size=m)
    rate = np.array([15.0, 50.0, 30.0, 60.0])
    h_fov = np.array([2 * np.pi, 4.71, 1.047, 1.5184])
    ares = np.array([0.00335, 0.00654, 0.00145, 0.00119])
    reach = np.array([100.0, 20.0, 50.0, 6.0])
    gain = np.array([1.0, 1.0, 0.4, 0.4])
    got = S.report_probability(dist, bearing, radius, rate, h_fov, ares, reach, gain, 0.5)
    want = report_probability_oracle(dist, bearing, radius, rate, h_fov, ares, reach, gain, 0.5)
    assert np.allclose(got, want)


def test_no_sensors_reports_nothing():
    z = np.zeros(0)
    p = S.report_probability(np.ones((3, 4)), np.zeros((3, 4)), np.ones(4), z, z, z, z, z, 0.5)
    assert p.shape == (3, 4) and not p.any()


def test_visibility_only_touches_light_sensitive_sensors():
    bright = S.suite_arrays([{"update_rate": 15.0, "h_fov": 6.28, "ares": 0.003,
                              "max_range": 100.0, "light_sensitive": 0},
                             {"update_rate": 30.0, "h_fov": 1.047, "ares": 0.0014,
                              "max_range": 50.0, "light_sensitive": 1}], 1.0)
    dark = S.suite_arrays([{"update_rate": 15.0, "h_fov": 6.28, "ares": 0.003,
                            "max_range": 100.0, "light_sensitive": 0},
                           {"update_rate": 30.0, "h_fov": 1.047, "ares": 0.0014,
                            "max_range": 50.0, "light_sensitive": 1}], 0.25)
    assert bright[3][0] == dark[3][0] == 100.0        # the lidar keeps its range
    assert dark[3][1] == pytest.approx(12.5)          # the camera loses three quarters
    assert dark[4].tolist() == [1.0, 0.25]


# ------------------------------------------------------------------
# occupancy rasterisation against an explicit loop

def test_inflated_discs_matches_oracle():
    centre = np.array([[4.0, 6.0], [11.5, 3.25], [20.0, 20.0]])
    radius = np.array([0.6, 1.2, 1.8])
    got = S.inflated_discs(centre, radius).reshape(3, S.NCELL, S.NCELL)
    xs = S.cell_centres()
    want = np.zeros_like(got)
    # brute-force test oracle
    for m in range(3):
        for r in range(S.NCELL):
            for c in range(S.NCELL):
                d = np.hypot(xs[c] - centre[m, 0], xs[r] - centre[m, 1])
                want[m, r, c] = float(d <= radius[m] + S.ROBOT_HALF + S.PLAN_MARGIN)
    assert np.array_equal(got, want)


def test_rock_field_clears_start_and_goal():
    for clutter in (0.0, 0.5, 1.0):
        centre, radius = S.rock_field(11, clutter)
        for anchor in (S.START_XY, S.GOAL_XY):
            assert (np.linalg.norm(centre - anchor, axis=1) > radius + S.CLEARANCE).all()


def test_clutter_adds_rocks():
    counts = [len(S.rock_field(5, c)[0]) for c in (0.0, 0.4, 0.8)]
    assert counts[0] < counts[1] < counts[2]


# ------------------------------------------------------------------
# the closed loop

def suite(names):
    import catalogue
    by = {s["name"]: s for s in catalogue.SENSORS}
    return [{k: by[n][k] for k in catalogue.SUITE_KEYS} for n in names]


def test_a_robot_with_no_sensors_hits_something():
    out = S.simulate([], {"clutter": 0.6, "visibility": 1.0, "seed": 2, "n_draws": 4})
    assert out["success_rate"] == 0.0
    assert out["collision_rate"] == 1.0
    assert out["detection_distance"] == 0.0


def test_a_full_suite_crosses_the_field():
    out = S.simulate(suite(["VLP-16-A", "LMS111-b1", "D435", "Blackfly-A"]),
                     {"clutter": 0.5, "visibility": 1.0, "seed": 2, "n_draws": 4})
    assert out["success_rate"] == 1.0
    assert out["tortuosity"] >= 1.0
    assert out["time_to_goal"] < S.TIME_BUDGET


def test_darkness_costs_a_depth_camera_its_range_but_not_a_lidar():
    scenario = {"clutter": 0.5, "seed": 2, "n_draws": 6}
    depth_bright = S.simulate(suite(["D455"]), dict(scenario, visibility=1.0))
    depth_dark = S.simulate(suite(["D455"]), dict(scenario, visibility=0.25))
    lidar_bright = S.simulate(suite(["HDL-32E-B"]), dict(scenario, visibility=1.0))
    lidar_dark = S.simulate(suite(["HDL-32E-B"]), dict(scenario, visibility=0.25))
    assert depth_dark["detection_distance"] < depth_bright["detection_distance"]
    assert depth_dark["success_rate"] < depth_bright["success_rate"]
    measured = [k for k in lidar_bright if k != "visibility"]
    assert [lidar_dark[k] for k in measured] == [lidar_bright[k] for k in measured]


def test_the_same_trial_twice_gives_the_same_numbers():
    job = (suite(["VLP-16-A", "D435"]),
           {"clutter": 0.7, "visibility": 0.5, "seed": 9, "n_draws": 5})
    assert S.simulate(*job) == S.simulate(*job)


def test_catalogue_totals_reach_the_metrics():
    names = ["VLP-16-A", "LMS111-b1", "D435", "Blackfly-A"]
    out = S.simulate(suite(names), {"clutter": 0.3, "visibility": 1.0, "seed": 1, "n_draws": 2})
    assert out["cost"] == 15500.0
    assert out["n_sensors"] == 4
    assert 0.0 <= out["battery_soc"] <= 1.0


def test_failed_draws_are_charged_the_mission_budget():
    out = S.simulate([], {"clutter": 0.6, "visibility": 1.0, "seed": 2, "n_draws": 4})
    assert out["time_to_goal"] == pytest.approx(S.TIME_BUDGET)
    assert out["path_length"] == pytest.approx(S.LENGTH_BUDGET)
    assert out["tortuosity"] == pytest.approx(S.LENGTH_BUDGET / S.CHORD)
