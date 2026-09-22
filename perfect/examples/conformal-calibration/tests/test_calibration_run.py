"""The trial against the case study's own campaign and conformal functions.

Everything the trial reports has to be exactly what `cpnav` computes from the
same episodes, or a campaign run through PERFECT would not be producing the
calibration data the case study calibrates on. Each test below recomputes one
part of the relayed dictionary from the package directly.
"""

import numpy as np
import pytest
import yaml

import calibration_run as cr
from cpnav import campaign, conformal, planner, world

HERE = cr.HERE


def scenario(**over):
    s = yaml.safe_load(open(HERE + "/scenario.yaml"))
    s.update(over)
    return s


def detector(name, shift):
    return {"configuration": name, "shift": shift}


def test_the_rows_are_the_case_studys_own_campaign_rows():
    s = scenario(clutter="nominal", seed=5, n_episodes=3)
    d = detector("nominal", 0.0)
    m = cr.metrics(s, d)

    world.MIN_OBSTACLES, world.MAX_OBSTACLES = 5, 9
    rng = np.random.default_rng(s["base_seed"] + 5)
    rows, out = campaign.run_campaign(rng, 3, shift=0.0, every=s["frame_every"])

    assert np.allclose(np.array(m["rows"]), rows, atol=10.0 ** -cr.DECIMALS)
    assert m["status"] == out["status"].tolist()
    assert m["steps"] == out["steps"].tolist()
    assert m["detections"] == rows.shape[0]
    assert m["episodes"] == 3


def test_the_clutter_band_sets_how_many_obstacles_stand_in_the_arena():
    counts = {}
    for name in ("sparse", "nominal", "dense"):
        s = scenario(clutter=name, seed=2, n_episodes=6)
        _, rows, _ = cr.run(s, detector("sharp", -0.6))
        # one object slot per detection row; the arena with more obstacles is
        # seen from more of them
        counts[name] = len(np.unique(rows[:, [0, 2]], axis=0)) / 6.0
    assert counts["sparse"] < counts["nominal"] < counts["dense"]
    assert cr.settings(scenario(clutter="dense"), detector("nominal", 0.0))["band"] == (9, 13)


def test_the_summaries_are_the_ones_the_rows_and_the_episodes_carry():
    s = scenario(clutter="sparse", seed=8, n_episodes=4)
    m = cr.metrics(s, detector("nominal", 0.0))
    rows = np.array(m["rows"])
    status = np.array(m["status"])

    truth, detected = rows[:, 6:10], rows[:, 10:14]
    scores = conformal.scores(detected, truth)
    assert m["score_mean"] == pytest.approx(scores.mean(), abs=1e-3)
    assert m["score_max"] == pytest.approx(scores.max(), abs=1e-3)
    assert m["coverage_margin"] == pytest.approx(-m["score_max"])
    assert m["collisions"] == int((status == planner.COLLISION).sum())
    assert m["collision_rate"] == pytest.approx(m["collisions"] / 4.0)
    assert m["successes"] + m["collisions"] + m["stalls"] == 4


def test_a_degraded_detector_reports_worse_boxes_than_a_sharp_one():
    s = scenario(clutter="nominal", seed=1, n_episodes=6)
    sharp = cr.metrics(s, detector("sharp", -0.6))
    degraded = cr.metrics(s, detector("degraded", 1.0))
    assert degraded["score_mean"] > sharp["score_mean"]
    assert degraded["coverage_margin"] < sharp["coverage_margin"]


def test_the_counts_survive_the_templates_float_substitution():
    """PERFECT fills a template argument with float(value) where it can, so a
    seed arrives as 3.0 and an episode count as 2.0. Both have to come back as
    ints, since they index draws and size arrays."""
    s = cr.settings(scenario(clutter="dense", seed=3.0, n_episodes=2.0),
                    detector("nominal", 0.0))
    assert s["seed"] == 3 and isinstance(s["seed"], int)
    assert s["n_episodes"] == 2 and isinstance(s["n_episodes"], int)
    assert s["shift"] == 0.0


def test_the_row_columns_are_the_ones_the_case_study_names():
    assert cr.ROW_COLUMNS == list(planner.ROW_COLUMNS)
    assert len(cr.ROW_COLUMNS) == 14
    s = scenario(clutter="sparse", seed=0, n_episodes=1)
    m = cr.metrics(s, detector("nominal", 0.0))
    assert all(len(r) == 14 for r in m["rows"])
