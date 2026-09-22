"""The campaign driver, with a stand-in for the PERFECT server.

Every test here injects its own `get`/`post`, so nothing opens a socket.
"""

import json

import numpy as np
import pytest

import range_campaign as rc


def grid():
    return rc.expand(rc.parse_list("0.1,0.4,0.8"), rc.parse_slopes("15,authored"),
                     rc.parse_frictions("0.6/0.5"), rc.parse_list("0.1"),
                     rc.parse_list("7", int), 20.0)


# ------------------------------------------------------------------
# the grid

def test_flags_parse_into_the_axes():
    assert rc.parse_list("0.1,0.4,0.8") == [0.1, 0.4, 0.8]
    assert rc.parse_slopes("15,authored,none") == [15.0, "authored", "authored"]
    assert rc.parse_frictions("0.6/0.5,0.3/0.25") == [(0.6, 0.5), (0.3, 0.25)]


def test_grid_is_the_cross_product():
    points = grid()
    assert len(points) == 6
    assert sorted({p["obstacle_density"] for p in points}) == [0.1, 0.4, 0.8]
    assert sorted({str(p["max_slope_deg"]) for p in points}) == ["15.0", "authored"]
    assert {p["duration_s"] for p in points} == {20.0}
    assert all(isinstance(p["seed"], int) for p in points)


def test_every_grid_point_has_a_distinct_name():
    names = [rc.point_name(p) for p in grid()]
    assert len(set(names)) == len(names)


def test_an_extra_point_that_repeats_a_grid_point_collapses():
    points = grid()
    extra = dict(points[0])
    assert len(rc.dedupe(points + [extra])) == 6
    baseline = dict(points[0], obstacle_density=0.3)
    assert len(rc.dedupe(points + [baseline])) == 7


# ------------------------------------------------------------------
# the setup commands

def test_setup_commands_cover_the_database_library_designs_and_environments():
    points = grid()
    n = len(rc.PERFECT_CMD)
    cmds = rc.setup_commands(points, ["Carter v2.4"], "range")
    heads = [c[n] for c in cmds]
    assert heads[:3] == ["db", "db", "db"]
    assert heads.count("components") == 1
    assert heads.count("designs") == 1
    assert heads.count("environments") == 1 + len(points)

    creates = [c for c in cmds if c[n:n + 2] == ["environments", "create_from_template"]]
    assert len(creates) == len(points)
    kwargs = dict(a.split(":=") for a in creates[0][n + 3:] if ":=" in a)
    assert set(kwargs) == {"obstacle_density", "max_slope_deg", "friction_static",
                           "friction_dynamic", "restitution", "seed", "duration_s"}


def test_no_reset_leaves_the_database_alone():
    cmds = rc.setup_commands(grid(), ["Carter v2.4"], "range", reset_db=False)
    assert not any(c[len(rc.PERFECT_CMD)] == "db" for c in cmds)


def test_designs_are_created_from_implementations():
    n = len(rc.PERFECT_CMD)
    cmds = rc.setup_commands([], ["Carter v2.4"], "range")
    create = [c for c in cmds if c[n] == "designs"][0]
    assert create[n:] == ["designs", "create", "Carter v2.4", "-i",
                          "--name", "Carter v2.4", "--tag", "range"]


# ------------------------------------------------------------------
# the API calls

def test_experiment_payload_names_one_design_and_one_environment():
    assert rc.experiment_payload(3, 9, "range") == {
        "design_ids": [3], "environment_ids": [9], "tag": "range", "run": True}


class FakeServer:
    """Just enough of /api/v1 to drive the campaign."""

    def __init__(self, designs, environments, trials=None):
        self.designs = designs
        self.environments = environments
        self.posted = []
        self.trials = trials or {}
        self.next_id = 1

    def get(self, url):
        path = url.split("/api/v1")[-1]
        if path == "/designs":
            return [{"id": i, "name": n} for n, i in self.designs.items()]
        if path == "/environments":
            return [{"id": i, "name": n} for n, i in self.environments.items()]
        if path.startswith("/experiments/"):
            return self.trials[int(path.split("/")[2].split("?")[0])]
        raise AssertionError("unexpected GET " + url)

    def post(self, url, body):
        self.posted.append((url, body))
        experiment_id = self.next_id
        self.next_id += 1
        return {"experiments": [{"experiment_id": experiment_id,
                                 "design_id": body["design_ids"][0],
                                 "environment_id": body["environment_ids"][0],
                                 "trial_ids": [experiment_id]}]}


def test_submit_posts_one_experiment_per_grid_point():
    points = grid()
    server = FakeServer({"Carter v2.4": 1},
                        {rc.point_name(p): 10 + i for i, p in enumerate(points)})
    created = rc.submit("/api/v1", points, ["Carter v2.4"], "range",
                        get=server.get, post=server.post)
    assert len(created) == len(points)
    assert [u for u, _ in server.posted] == ["/api/v1/experiments"] * len(points)
    assert [b["environment_ids"][0] for _, b in server.posted] == list(range(10, 16))
    assert all(b["design_ids"] == [1] for _, b in server.posted)
    assert {c["design"] for c in created} == {"Carter v2.4"}


def test_submit_stops_when_a_design_is_missing():
    server = FakeServer({}, {})
    with pytest.raises(SystemExit):
        rc.submit("/api/v1", grid()[:1], ["Carter v2.4"], "range",
                  get=server.get, post=server.post)


def test_wait_for_returns_as_soon_as_every_trial_is_terminal():
    calls = []

    def get(url):
        calls.append(url)
        return {"last_trial_state": "TrialState.SUCCESSFUL|SHUT_DOWN"}

    final = rc.wait_for("/api/v1", [1, 2], timeout=60, get=get, sleep=lambda s: None)
    assert set(final) == {1, 2}
    assert len(calls) == 2


def test_wait_for_gives_up_at_the_deadline():
    slept = []

    def get(url):
        return {"last_trial_state": "TrialState.RUNNING"}

    final = rc.wait_for("/api/v1", [1], timeout=0.0, get=get, sleep=slept.append)
    assert final == {1: "TrialState.RUNNING"}
    assert slept == []


# ------------------------------------------------------------------
# collecting

def updates(pairs):
    return [{"timestamp": i, "data": {"update": k, "data": v}}
            for i, (k, v) in enumerate(pairs)]


def test_the_last_value_of_a_relayed_name_wins_and_the_stopwatch_is_dropped():
    m = rc.trial_metrics(updates([("start_age", 1.0), ("distance_m", 2.0),
                                  ("start_age", 2.0), ("distance_m", 7.5),
                                  ("state", 512)]))
    assert m == {"distance_m": 7.5}


def test_environment_knobs_come_from_the_specification():
    spec = {"doe": {"obstacle_density": 0.4, "max_slope_deg": "authored"},
            "drive": {"duration_s": 20.0}, "start": {"x": 0, "y": 0}}
    assert rc.environment_knobs(spec) == {"obstacle_density": 0.4,
                                          "max_slope_deg": "authored",
                                          "duration_s": 20.0}


def collect_server(state="TrialState.SUCCESSFUL|SHUT_DOWN"):
    experiment = {
        "id": 1,
        "design": {"name": "Carter v2.4"},
        "environment": {"name": "density 0.4, slope authored, friction 0.6/0.5, seed 7",
                        "specification": {"doe": {"obstacle_density": 0.4,
                                                  "max_slope_deg": "authored",
                                                  "friction_static": 0.6,
                                                  "friction_dynamic": 0.5,
                                                  "restitution": 0.1, "seed": 7},
                                          "drive": {"duration_s": 20.0}}},
        "trials": [{"id": 5, "state": state}],
    }
    trial = {"id": 5, "updates": updates([("distance_m", 9.25), ("max_pitch_deg", 11.0),
                                          ("stuck", False), ("run_dir", "/somewhere")])}

    def get(url):
        path = url.split("/api/v1")[-1]
        if path == "/experiments":
            return [{"id": 1}]
        if path.startswith("/experiments/"):
            return experiment
        if path.startswith("/trials/"):
            assert "updates=" in path
            return trial
        raise AssertionError("unexpected GET " + url)

    return get


def test_collect_makes_one_row_per_trial_with_knobs_and_metrics():
    rows = rc.collect("/api/v1", get=collect_server())
    assert len(rows) == 1
    row = rows[0]
    assert row["trial_id"] == 5
    assert row["state"] == "SUCCESSFUL|SHUT_DOWN"
    assert row["design"] == "Carter v2.4"
    assert row["obstacle_density"] == 0.4
    assert row["max_slope_deg"] == "authored"
    assert row["duration_s"] == 20.0
    assert row["distance_m"] == 9.25
    assert row["max_pitch_deg"] == 11.0


def test_csv_round_trip_keeps_every_field(tmp_path):
    rows = rc.collect("/api/v1", get=collect_server())
    path = tmp_path / "campaign.csv"
    columns = rc.write_csv(rows, path)
    assert columns[:5] == rc.LEAD_COLUMNS[:5]
    assert "run_dir" in columns
    back = rc.read_csv(path)
    assert len(back) == 1
    assert back[0]["max_slope_deg"] == "authored"
    assert float(back[0]["distance_m"]) == 9.25
    assert set(back[0]) == set(columns)


def test_column_reads_numbers_and_marks_the_gaps():
    rows = [{"distance_m": "1.5"}, {"distance_m": ""}, {}]
    values = rc.column(rows, "distance_m")
    assert values[0] == 1.5
    assert np.isnan(values[1:]).all()


def test_the_campaign_grid_survives_a_json_round_trip():
    points = grid()
    assert json.loads(json.dumps(points)) == points


def test_trajectories_are_copied_next_to_the_table_and_found_again(tmp_path):
    run_dir = tmp_path / "trial_5"
    run_dir.mkdir()
    (run_dir / "trajectory.csv").write_text("t,x,y,z,roll,pitch,yaw,v\n0,1,2,3,0,0,0,0\n")
    rows = [{"trial_id": 5, "run_dir": str(run_dir)}, {"trial_id": 6, "run_dir": "/nowhere"}]
    rc.copy_trajectories(rows, tmp_path / "results" / "trajectories")
    assert rows[0]["trajectory"] == "trajectories/trial_5.csv"
    assert "trajectory" not in rows[1]
    assert rc.trajectory_path(rows[0], tmp_path / "results").exists()
    assert not rc.trajectory_path(rows[1], tmp_path / "results").exists()


def test_the_table_names_files_by_run_directory_only():
    row = rc.strip_machine_paths({
        "run_dir": "/somewhere/deep/range/doe/runs/trial_3",
        "design_point": "/somewhere/deep/range/doe/runs/trial_3/layer.usda",
        "layer": "/somewhere/deep/range/doe/runs/trial_3/layer.usda"})
    assert row == {"run_dir": "trial_3", "design_point": "trial_3/layer.usda",
                   "layer": "trial_3/layer.usda"}
