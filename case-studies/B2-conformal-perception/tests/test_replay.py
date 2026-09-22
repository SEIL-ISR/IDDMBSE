"""The per-step hook, the path descent and the replay of the figure episode."""

import pathlib
import subprocess
import sys

import numpy as np

from cpnav import campaign, planner, replay, world

root = pathlib.Path(__file__).resolve().parents[1]


def test_the_hook_leaves_the_run_unchanged_and_sees_every_step():
    boxes, valid, hard = campaign.feasible_worlds(np.random.default_rng(3), 6)
    plain = planner.run_episodes(np.random.default_rng(9), boxes, valid, hard, q=0.4)
    steps = []
    hooked = planner.run_episodes(np.random.default_rng(9), boxes, valid, hard, q=0.4,
                                  on_step=steps.append)
    for key in ["status", "length", "steps", "waits", "traj"]:
        assert np.array_equal(plain[key], hooked[key])
    assert np.array_equal(np.stack([s["xy"] for s in steps], axis=1), hooked["traj"][:, 1:])
    assert np.array_equal(np.stack([s["xy_before"] for s in steps], axis=1),
                          hooked["traj"][:, :-1])
    assert [s["t"] for s in steps] == list(range(len(steps)))


def test_descent_on_an_empty_grid_runs_from_start_to_goal():
    d = planner.cost_to_go(np.zeros((1, world.NCELL, world.NCELL), dtype=bool))
    cells, used = planner.descend(d, np.array([world.START_RC]))
    path = cells[0, :used[0]]
    assert tuple(path[0]) == world.START_RC
    assert tuple(path[-1]) == world.GOAL_RC
    assert used[0] == 36    # 35 diagonal moves from (2, 2) to (37, 37)


def test_the_plan_starts_with_the_move_the_robot_makes():
    boxes, valid, hard = campaign.feasible_worlds(np.random.default_rng(4), 4)
    steps = []
    planner.run_episodes(np.random.default_rng(2), boxes, valid, hard, q=0.3,
                         on_step=steps.append)
    s = steps[0]
    cells, used = planner.descend(s["cost_to_go"], s["rc_before"])
    moved = np.any(s["xy"] != s["xy_before"], axis=1)
    first_xy = (cells[:, 1, ::-1] + 0.5) * world.RES
    assert np.allclose(first_xy[moved], s["xy"][moved])


def test_the_replay_is_the_studys_figure_episode():
    r = replay.figure_pair()
    op = r["summary"]["operating_point"]
    assert r["q"] == op["q_m"]
    assert r["closed_loop_coverage"] == op["closed_loop_coverage"]
    status = r["pair"]["status"].reshape(2, replay.N_FIGURE)
    picked = np.nonzero((status[0] == planner.COLLISION) & (status[1] == planner.SUCCESS))[0]
    assert picked[0] == r["summary"]["figure_episode"]


def test_the_animation_script_writes_its_files(tmp_path):
    script = root / "animations" / "make_conformal_regions.py"
    r = subprocess.run([sys.executable, str(script), "--out", str(tmp_path), "--frames", "4"],
                       capture_output=True, text=True, cwd=root)
    assert r.returncode == 0, r.stderr
    assert "frames 4" in r.stdout
    for name in ["conformal_regions.mp4", "conformal_regions.gif",
                 "conformal_regions_poster.pdf"]:
        assert (tmp_path / name).stat().st_size > 1000
    svg = (tmp_path / "conformal_regions_poster.svg").read_text()
    assert svg.count("<path") > 20
