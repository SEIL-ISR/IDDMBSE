import numpy as np

from cpnav import campaign, conformal, planner, world


def test_feasible_worlds_are_solvable_with_true_boxes():
    rng = np.random.default_rng(2)
    boxes, valid, hard = campaign.feasible_worlds(rng, 24)
    assert boxes.shape == (24, world.MAX_OBSTACLES, 4)
    grown = conformal.inflate(boxes, world.ROBOT_HALF)
    d = planner.cost_to_go(planner.rasterise(grown, valid))
    assert np.all(np.isfinite(d[:, world.START_RC[0], world.START_RC[1]]))


def test_campaign_rows_have_the_documented_shape(tmp_path):
    rng = np.random.default_rng(4)
    rows, _ = campaign.run_campaign(rng, 4, every=4)
    assert rows.shape[1] == len(planner.ROW_COLUMNS)
    assert rows.shape[0] > 0
    assert set(np.unique(rows[:, 0]).astype(int)).issubset({0, 1, 2, 3})

    path = tmp_path / "campaign.csv"
    campaign.write_rows(path, rows)
    back = campaign.read_rows(path)
    assert np.allclose(back, rows, atol=1e-4)

    cal, hold = campaign.split_by_episode(rows, 2)
    assert cal.shape[0] + hold.shape[0] == rows.shape[0]
    assert cal[:, 0].max() < 2
    assert hold[:, 0].min() >= 2


def test_detections_are_only_reported_inside_the_sensor_range():
    from cpnav import detector

    rng = np.random.default_rng(6)
    boxes, valid, hard = campaign.feasible_worlds(rng, 8)
    robot = np.tile(world.START_XY, (8, 1))
    det, det_valid, dist = detector.detect(rng, boxes, valid, hard, robot)
    assert not np.any(det_valid & (dist > detector.MAX_RANGE))
    assert np.array_equal(det_valid, valid & (dist <= detector.MAX_RANGE))


def test_the_detector_underestimates_box_size_on_average():
    from cpnav import detector

    rng = np.random.default_rng(8)
    boxes, valid, hard = campaign.feasible_worlds(rng, 64)
    robot = np.tile(world.START_XY, (64, 1))
    det, det_valid, _ = detector.detect(rng, boxes, valid, hard, robot)
    true_area = np.prod(boxes[:, :, 2:] - boxes[:, :, :2], axis=2)[det_valid]
    det_area = np.prod(det[:, :, 2:] - det[:, :, :2], axis=2)[det_valid]
    assert det_area.mean() < true_area.mean()
    assert conformal.scores(det[det_valid], boxes[det_valid]).mean() > 0.0


def test_no_rows_are_recorded_after_an_episode_has_ended():
    # An episode that collides early is frozen at its terminal pose; if it kept
    # reporting detections it would flood the calibration table with repeats of
    # one state.
    rng = np.random.default_rng(12)
    boxes, valid, hard = campaign.feasible_worlds(rng, 12)
    out = planner.run_episodes(rng, boxes, valid, hard, q=0.0, record=True)
    rows = out["rows"]
    last_step = np.zeros(12)
    np.maximum.at(last_step, rows[:, 0].astype(int), rows[:, 1])
    live_steps = out["steps"] + out["waits"]
    assert np.all(last_step < live_steps)
    assert live_steps.min() < live_steps.max()   # the episodes really do differ in length


def test_distribution_shift_makes_the_detector_worse():
    from cpnav import conformal, detector

    rng = np.random.default_rng(9)
    boxes, valid, hard = campaign.feasible_worlds(rng, 128)
    robot = np.tile(world.START_XY, (128, 1))
    plain, seen, _ = detector.detect(rng, boxes, valid, hard, robot, shift=0.0)
    shifted, seen2, _ = detector.detect(rng, boxes, valid, hard, robot, shift=1.0)
    assert np.array_equal(seen, seen2)   # the range gate does not move
    s0 = conformal.scores(plain[seen], boxes[seen])
    s1 = conformal.scores(shifted[seen], boxes[seen])
    assert s1.mean() > s0.mean()
    assert conformal.quantile(s1, 0.1) > conformal.quantile(s0, 0.1)
