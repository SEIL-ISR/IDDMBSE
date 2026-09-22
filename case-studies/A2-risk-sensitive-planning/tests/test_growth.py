"""The growth-recording hook and the animation built on it."""

import csv
import pathlib
import subprocess
import sys

import numpy as np
import yaml

from rarrt.growth import best_path, record_growth
from rarrt.rrtstar import CostModel, path_geometry, plan
from rarrt.world import make_world

root = pathlib.Path(__file__).resolve().parents[1]


def test_recording_leaves_the_plan_unchanged():
    world = make_world(0.16, seed=3)
    cost = CostModel(sigma=0.5, alpha=0.9, seed=4)
    plain = plan(world, cost, iterations=500, seed=8)
    recorded, snaps = record_growth(world, cost, [0, 250, 500], iterations=500, seed=8)
    assert np.array_equal(plain["path"], recorded["path"])
    assert plain["cost"] == recorded["cost"]
    assert plain["nodes"] == recorded["nodes"]
    assert [s["iteration"] for s in snaps] == [0, 250, 500]
    assert snaps[0]["points"].shape == (1, 2)


def test_the_recorded_final_tree_is_the_planners_tree():
    world = make_world(0.26, seed=0)
    cost = CostModel(sigma=0.5, alpha=None, seed=1)
    kept = plan(world, cost, iterations=700, seed=5, keep_tree=True)
    result, snaps = record_growth(world, cost, [700], iterations=700, seed=5)
    final = snaps[-1]
    assert np.array_equal(final["points"], kept["tree_points"])
    assert np.array_equal(final["parent"], kept["tree_parent"])
    path, c = best_path(world, cost, final["points"], final["parent"], final["cost_to"], 3.0)
    assert np.array_equal(path, result["path"])
    assert c == result["cost"]


def test_the_tree_only_grows_and_the_best_path_cost_never_rises():
    world = make_world(0.16, seed=2)
    cost = CostModel(sigma=0.3, alpha=0.5, seed=5)
    _, snaps = record_growth(world, cost, np.arange(0, 901, 50), iterations=900, seed=11)
    sizes = np.array([s["points"].shape[0] for s in snaps])
    assert (np.diff(sizes) >= 0).all()
    costs = np.array([best_path(world, cost, s["points"], s["parent"], s["cost_to"], 3.0)[1]
                      for s in snaps])
    found = np.isfinite(costs)
    assert found[-1]
    assert (np.diff(costs[found]) <= 1e-9).all()


def test_the_animated_runs_reproduce_their_campaign_rows():
    cfg = yaml.safe_load((root / "campaign.yaml").read_text())
    rows = {r["policy"]: r for r in csv.DictReader(open(root / "results" / "campaign.csv"))
            if r["env"] == "hard" and r["sigma"] == "0.5" and r["run"] == "0"}
    world = make_world(0.26, seed=0, half_width=cfg["half_width"])
    for policy, alpha in [("rrtstar", None), ("cvar0.9", 0.9)]:
        cost = CostModel(sigma=0.5, alpha=alpha, n_samples=cfg["n_samples"], kappa=cfg["kappa"],
                         d_hazard=cfg["d_hazard"], p_max=cfg["p_max"], seed=cfg["crn_seed"])
        result, _ = record_growth(world, cost, [cfg["iterations"]], iterations=cfg["iterations"],
                                  step=cfg["step"], goal_bias=cfg["goal_bias"],
                                  seed=cfg["plan_seed"])
        lengths, clearances = path_geometry(world, result["path"])
        assert np.isclose(lengths.sum(), float(rows[policy]["nominal_length"]))
        assert np.isclose(clearances.min(), float(rows[policy]["min_clearance"]))


def test_the_animation_script_writes_its_files(tmp_path):
    script = root / "animations" / "make_rarrt_tree_growth.py"
    r = subprocess.run([sys.executable, str(script), "--out", str(tmp_path), "--frames", "4"],
                       capture_output=True, text=True, cwd=root)
    assert r.returncode == 0, r.stderr
    assert "frames 4" in r.stdout
    for name in ["rarrt_tree_growth.mp4", "rarrt_tree_growth.gif",
                 "rarrt_tree_growth_poster.pdf"]:
        assert (tmp_path / name).stat().st_size > 1000
    svg = (tmp_path / "rarrt_tree_growth_poster.svg").read_text()
    assert svg.count("<path") > 50
