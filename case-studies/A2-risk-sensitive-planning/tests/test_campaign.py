import csv

import numpy as np

from rarrt.campaign import FIELDS, build_tasks, run_campaign


def tiny_config():
    return {
        "environments": [("easy", 0.08), ("hard", 0.26)],
        "noise_levels": [0.1],
        "policies": [("rrtstar", None), ("cvar0.9", 0.9)],
        "runs": 2,
        "iterations": 250,
        "step": 3.0,
        "goal_bias": 0.05,
        "half_width": 32.0,
        "n_samples": 64,
        "kappa": 20.0,
        "d_hazard": 2.0,
        "p_max": 0.15,
        "n_exec": 20,
        "budget_factor": 1.5,
        "crn_seed": 1000,
        "plan_seed": 50000,
        "exec_seed": 90000,
        "straight_line": float(np.hypot(56.0, 56.0)),
    }


def test_the_task_list_is_the_product_of_the_grid():
    cfg = tiny_config()
    assert len(build_tasks(cfg)) == 2 * 1 * 2 * 2


def test_the_campaign_writes_the_expected_csv_columns(tmp_path):
    cfg = tiny_config()
    path = tmp_path / "campaign.csv"
    rows, cells = run_campaign(cfg, processes=2, csv_path=path)

    assert len(rows) == 8
    with open(path) as handle:
        written = list(csv.DictReader(handle))
    assert list(written[0].keys()) == FIELDS
    assert len(written) == 8
    assert {r["policy"] for r in written} == {"rrtstar", "cvar0.9"}
    assert {r["env"] for r in written} == {"easy", "hard"}

    assert len(cells) == 4
    for cell in cells:
        assert cell["runs"] == 2
        assert 0.0 <= cell["success_rate"] <= 1.0
        assert 0.0 <= cell["failure_rate"] <= 1.0


def test_the_campaign_reproduces_exactly_apart_from_the_timings():
    cfg = tiny_config()
    first, _ = run_campaign(cfg, processes=2)
    second, _ = run_campaign(cfg, processes=2)
    keys = [f for f in FIELDS if f not in ("plan_time",)]
    assert [[r[k] for k in keys] for r in first] == [[r[k] for k in keys] for r in second]
