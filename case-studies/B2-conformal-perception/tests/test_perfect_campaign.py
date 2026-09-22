"""The PERFECT campaign driver, without a server.

Every function tested here is pure: the grid it submits, the detection table it
builds out of collected trials, and the calibration it runs on that table. The
trials themselves are made up in `collected()` below, in exactly the shape
`tradesx.ddo_api.collect` returns them, with a detector whose nonconformity is a
known draw so the coverage the calibration reaches can be checked against the
level it asked for.
"""

import csv

import numpy as np
import pytest

import run_perfect_campaign as R

SCALE = {"sharp": 0.3, "nominal": 1.0, "degraded": 2.5}


def trial_rows(rng, detector, n_detections):
    """Detections whose nonconformity score is a known exponential draw.

    The detection is the true box shrunk by the same amount on all four edges,
    so the score of `cpnav.conformal` is exactly that amount.
    """
    centre = rng.uniform(3.0, 17.0, size=(n_detections, 2))
    half = np.full((n_detections, 2), 0.8)
    truth = np.concatenate([centre - half, centre + half], axis=1)
    pad = SCALE[detector] * rng.exponential(0.2, size=(n_detections, 1))
    detected = truth + np.concatenate([pad, pad, -pad, -pad], axis=1)

    table = np.zeros((n_detections, len(R.ROW_COLUMNS)))
    table[:, 1] = np.arange(n_detections)
    table[:, 2] = np.arange(n_detections)
    table[:, 3:5] = centre
    table[:, 5] = np.linalg.norm(centre, axis=1)
    table[:, 6:10] = truth
    table[:, 10:14] = detected
    return table, pad.ravel()


def collected(seed=0, n_detections=14):
    rng = np.random.default_rng(seed)
    rows = []
    trial = 1
    for detector in R.detectors():
        for clutter in R.CLUTTER:
            for s in R.SEEDS:
                table, _ = trial_rows(rng, detector, n_detections)
                collisions = int(rng.random() < 0.6)
                rows.append({
                    "design": detector,
                    "environment": clutter + "-seed" + str(s),
                    "experiment_id": trial, "trial_id": trial,
                    "state": "TrialState.SUCCESSFUL|SHUT_DOWN", "wall_seconds": 1.0,
                    "detector": detector, "shift": 0.0, "clutter": clutter, "seed": s,
                    "episodes": 1, "detections": n_detections,
                    "collisions": collisions, "successes": 1 - collisions, "stalls": 0,
                    "collision_rate": float(collisions), "success_rate": 1.0 - collisions,
                    "mean_length": 22.0, "mean_waits": 0.0,
                    "score_mean": 0.1, "score_max": 0.3, "coverage_margin": -0.3,
                    "rows": table.tolist(),
                })
                trial += 1
    return rows


def test_the_grid_is_every_detector_against_every_environment():
    designs = R.campaign_designs()
    environments = R.campaign_environments()
    assert len(designs) == 3
    assert len(environments) == len(R.CLUTTER) * len(R.SEEDS)
    assert len(designs) * len(environments) == 270
    for name, components in designs.items():
        assert components == [name]


def test_each_environment_carries_the_three_template_arguments():
    for key, arguments in R.campaign_environments().items():
        assert sorted(arguments) == ["clutter", "n_episodes", "seed"]
        assert key.startswith(arguments["clutter"])
        assert arguments["n_episodes"] == R.N_EPISODES
        assert arguments["seed"] in R.SEEDS
    assert len(R.campaign_environments()) == 90


def test_the_detections_of_every_trial_land_in_one_table():
    rows = collected()
    where, table = R.detection_table(rows)
    assert table.shape == (sum(len(r["rows"]) for r in rows), len(R.ROW_COLUMNS))
    for key in ("trial_id", "detector", "clutter", "seed"):
        assert where[key].shape[0] == table.shape[0]
    first = rows[0]
    assert (where["trial_id"] == first["trial_id"]).sum() == len(first["rows"])
    assert set(where["detector"].tolist()) == set(R.detectors())


def test_the_split_is_taken_over_whole_trials_of_one_detector():
    rows = collected()
    where, _ = R.detection_table(rows)
    calibration, holdout, by_detector = R.masks(where)
    assert not (calibration & holdout).any()
    assert set(where["detector"][calibration].tolist()) == {R.CALIBRATION_DETECTOR}
    assert set(where["detector"][holdout].tolist()) == {R.CALIBRATION_DETECTOR}
    assert where["seed"][calibration].max() < R.N_CALIBRATION_SEEDS
    assert where["seed"][holdout].min() >= R.N_CALIBRATION_SEEDS
    assert sum(m.sum() for m in by_detector) == where["detector"].shape[0]


def test_the_calibration_reaches_the_coverage_it_asked_for():
    rows = collected()
    where, table = R.detection_table(rows)
    coverage, qs, cal_scores = R.coverage_table(where, table)

    assert [r[0] for r in coverage] == R.ALPHAS
    assert qs == sorted(qs)          # a smaller alpha asks for a larger quantile
    n = int(where["detector"].shape[0] / 3 * (R.N_CALIBRATION_SEEDS / len(R.SEEDS)))
    assert coverage[0][3] == n
    for alpha, r in zip(R.ALPHAS, coverage):
        held = r[5]
        # binomial spread on the held-out rows, generously bounded
        assert abs(held - (1.0 - alpha)) < 5.0 * np.sqrt(alpha * (1 - alpha) / r[4])
        assert r[6] <= held <= r[7]


def test_a_sharper_detector_covers_more_and_a_degraded_one_less():
    rows = collected()
    where, table = R.detection_table(rows)
    coverage, _, _ = R.coverage_table(where, table)
    order = R.detectors()
    for r in coverage:
        by_detector = dict(zip(order, r[8:]))
        assert by_detector["sharp"] > by_detector["nominal"] > by_detector["degraded"]


def test_the_tables_are_byte_identical_when_written_twice(tmp_path):
    rows = collected()
    where, table = R.detection_table(rows)
    first, second = tmp_path / "a.csv", tmp_path / "b.csv"

    R.write_detections(where, table, first)
    R.write_detections(where, table, second)
    assert first.read_bytes() == second.read_bytes()
    with open(first) as f:
        written = list(csv.reader(f))
    assert written[0] == ["trial_id", "detector", "clutter", "seed"] + R.ROW_COLUMNS
    assert len(written) == table.shape[0] + 1

    R.write_episodes(rows, first)
    R.write_episodes(rows, second)
    assert first.read_bytes() == second.read_bytes()

    coverage, _, _ = R.coverage_table(where, table)
    R.write_coverage(coverage, first)
    R.write_coverage(coverage, second)
    assert first.read_bytes() == second.read_bytes()


def test_every_trial_carries_the_two_numbers_a_safety_report_reads():
    """`collisions` decides the outcome of a trial and `coverage_margin` is the
    number summarised beside it, so both have to be on every row."""
    for r in collected():
        assert r["collisions"] in (0, 1)
        assert r["collisions"] + r["successes"] + r["stalls"] == r["episodes"]
        assert isinstance(r["coverage_margin"], float)
    assert "collisions" in R.EPISODE_COLUMNS and "coverage_margin" in R.EPISODE_COLUMNS


def test_the_collision_rate_table_covers_every_detector_and_band():
    rates = R.collision_rates(collected())
    assert sorted(rates) == sorted(R.detectors())
    for values in rates.values():
        assert len(values) == len(R.CLUTTER)
        assert all(0.0 <= v <= 1.0 for v in values)


def test_the_clutter_bands_are_the_ones_the_example_declares():
    assert R.band("sparse") == (3, 5)
    assert R.band("dense") == (9, 13)
    assert R.band(R.TEST_CLUTTER)[0] <= R.band(R.TEST_CLUTTER)[1]


def test_the_score_of_a_shrunken_box_is_how_far_it_was_shrunk():
    rng = np.random.default_rng(1)
    table, pad = trial_rows(rng, "nominal", 20)
    assert R.scores_of(table, np.ones(20, dtype=bool)) == pytest.approx(pad)
