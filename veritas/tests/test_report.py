"""The campaign report tool: grouping, the per-group bounds, and the files it writes.

The fixture is a SQLite database built from PERFECT's own schema, with two designs, two
environments and a robustness payload per trial in the `update` table -- the same shape
`report.py` meets on a database a real campaign left behind.
"""

import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest
from scipy import stats

import campaign_stats as cs
import perfect_adapter as pa
import report

root = Path(__file__).resolve().parents[1]

SCHEMA = """
create table design (
    id integer not null, name varchar(32), tag varchar(16), template_id varchar(16),
    implementation json, primary key (id), unique (name));
create table environment (
    id integer not null, name varchar(32), tag varchar(16), specification json,
    template_id integer, primary key (id), unique (name));
create table experiment (
    id integer not null, design_id integer not null, environment_id integer not null,
    tag varchar(16), primary key (id),
    foreign key(design_id) references design (id),
    foreign key(environment_id) references environment (id));
create table trial (
    id integer not null, datetime datetime, uri varchar(32), state varchar, start_age float,
    sim_time float, cancelled_by varchar, job_id varchar(36), experiment_id integer not null,
    primary key (id), foreign key(experiment_id) references experiment (id));
create table "update" (
    id integer not null, trial_id integer not null, timestamp float not null,
    payload_json text not null, primary key (id),
    foreign key(trial_id) references trial (id));
"""

PER_GROUP = 40
MEANS = np.array([0.30, 0.10, 0.25, 0.05])   # (design, environment) in experiment order


@pytest.fixture(scope="module")
def campaign(tmp_path_factory):
    rng = np.random.default_rng(7)
    rho = rng.normal(np.repeat(MEANS, PER_GROUP), 0.12)
    success = rho >= 0
    experiment = np.repeat(np.arange(1, MEANS.size + 1), PER_GROUP)
    trial_ids = np.arange(1, rho.size + 1)

    path = tmp_path_factory.mktemp("campaign") / "campaign.db"
    con = sqlite3.connect(path)
    con.executescript(SCHEMA)
    con.executemany("insert into design values (?,?,'demo',null,'[]')",
                    [(1, "planner A"), (2, "planner B")])
    con.executemany("insert into environment values (?,?,'demo','{}',null)",
                    [(1, "sparse"), (2, "dense")])
    con.executemany("insert into experiment values (?,?,?,'demo')",
                    [(1, 1, 1), (2, 1, 2), (3, 2, 1), (4, 2, 2)])
    con.executemany("insert into trial (id, state, start_age, experiment_id) values (?,?,?,?)",
                    zip(trial_ids.tolist(),
                        np.where(success, "TrialState.SUCCESSFUL|SHUT_DOWN",
                                 "TrialState.ERRORED|SHUT_DOWN").tolist(),
                        np.full(rho.size, 12.0).tolist(), experiment.tolist()))
    con.executemany('insert into "update" values (?,?,?,?)',
                    [(int(i), int(i), 0.0, json.dumps(
                        {"update": "robustness", "trial_id": int(i), "data": float(r)}))
                     for i, r in zip(trial_ids, rho)])
    con.commit()
    con.close()
    return {"path": path, "rho": rho, "success": success, "experiment": experiment}


def test_the_metric_comes_back_aligned_to_the_trials(campaign):
    c = pa.read_campaign(str(campaign["path"]))
    rho = pa.read_metric(str(campaign["path"]), c["trial_id"])
    assert np.allclose(rho, campaign["rho"])
    assert c["environment_name"].tolist()[:PER_GROUP] == ["sparse"] * PER_GROUP


def test_a_trial_with_no_payload_is_nan_and_the_last_payload_wins(tmp_path):
    path = tmp_path / "small.db"
    con = sqlite3.connect(path)
    con.executescript(SCHEMA)
    con.execute("insert into design values (1,'d','demo',null,'[]')")
    con.execute("insert into environment values (1,'e','demo','{}',null)")
    con.execute("insert into experiment values (1,1,1,'demo')")
    con.executemany("insert into trial (id, state, experiment_id) values (?,?,1)",
                    [(1, "TrialState.SUCCESSFUL"), (2, "TrialState.SUCCESSFUL"),
                     (3, "TrialState.ERRORED")])
    con.executemany('insert into "update" values (?,?,?,?)', [
        (1, 1, 0.0, json.dumps({"update": "robustness", "trial_id": 1, "data": 0.1})),
        (2, 1, 1.0, json.dumps({"update": "robustness", "trial_id": 1, "data": 0.4})),
        (3, 2, 0.0, json.dumps({"update": "state", "trial_id": 2, "data": "x"})),
        (4, 3, 0.0, json.dumps({"robustness": -0.2})),
    ])
    con.commit()
    con.close()
    rho = pa.read_metric(str(path), [1, 2, 3])
    assert rho[0] == pytest.approx(0.4)      # the later payload of trial 1
    assert np.isnan(rho[1])                  # no robustness payload at all
    assert rho[2] == pytest.approx(-0.2)     # the flat `{"robustness": ...}` shape

    # a database with no update table at all is all-nan, not an error
    plain = tmp_path / "plain.db"
    con = sqlite3.connect(plain)
    con.executescript("create table trial (id integer primary key);")
    con.close()
    assert np.all(np.isnan(pa.read_metric(str(plain), [1, 2])))


def test_grouping_matches_the_campaign_report_group_by_group(campaign):
    c = pa.read_campaign(str(campaign["path"]))
    rho = pa.read_metric(str(campaign["path"]), c["trial_id"])
    s = report.summarise(c["success"], c["design_name"], c["environment_name"], rho=rho)

    assert [" | ".join(g) for g in s["groups"]] == [
        "planner A | dense", "planner A | sparse", "planner B | dense", "planner B | sparse"]
    assert s["trials"].tolist() == [PER_GROUP] * 4

    # brute-force oracle: split the campaign by hand and run the single-campaign report on
    # each piece; every grouped number must agree with it
    for i, (design, environment) in enumerate(s["groups"]):
        m = (c["design_name"].astype(str) == design) & (c["environment_name"].astype(str) == environment)
        ref = cs.campaign_report(c["success"][m], rho=rho[m], delta=0.05, target=0.05)
        assert s["failures"][i] == ref["failures"]
        assert s["failure_rate"][i] == pytest.approx(ref["failure_rate"])
        assert s["clopper_pearson_lo"][i] == pytest.approx(ref["clopper_pearson"][0])
        assert s["clopper_pearson_hi"][i] == pytest.approx(ref["clopper_pearson"][1])
        assert s["wilson_lo"][i] == pytest.approx(ref["wilson"][0])
        assert s["trials_for_target"][i] == ref["trials_for_target"]
        b = s["robustness"]
        assert b["mean"][i] == pytest.approx(ref["robustness"]["mean"])
        assert b["min"][i] == pytest.approx(ref["robustness"]["min"])
        assert b["violated"][i] == pytest.approx(ref["robustness"]["violated"])
        assert b["quantile"][i] == pytest.approx(ref["robustness"]["quantile"])
        assert b["quantile_dkw"][i] == ref["robustness"]["quantile_dkw"]


def test_the_group_bounds_are_the_binomial_ones(campaign):
    """scipy.stats.binom as the independent oracle for one group's exact interval."""
    c = pa.read_campaign(str(campaign["path"]))
    s = report.summarise(c["success"], c["design_name"], c["environment_name"], delta=0.05)
    i = 0
    k, n = int(s["failures"][i]), int(s["trials"][i])
    assert k > 0
    # the exact interval endpoints are the p at which the binomial tails equal delta/2
    assert stats.binom.sf(k - 1, n, s["clopper_pearson_lo"][i]) == pytest.approx(0.025)
    assert stats.binom.cdf(k, n, s["clopper_pearson_hi"][i]) == pytest.approx(0.025)
    assert stats.binom.cdf(k, n, s["clopper_pearson_upper"][i]) == pytest.approx(0.05)


def test_the_vectorised_trials_needed_matches_the_scalar_one():
    """The scalar `trials_for_upper_bound` is the oracle for the array version."""
    k = np.array([0, 1, 2, 5, 17, 204])
    got = cs.trials_for_upper_bound_array(0.05, 0.05, k)
    want = [cs.trials_for_upper_bound(0.05, 0.05, failures=int(v)) for v in k]
    assert got.tolist() == want
    # and the bound really is reached at n and not at n - 1
    assert np.all(cs.clopper_pearson_upper(k, got, 0.05) <= 0.05)
    assert np.all(cs.clopper_pearson_upper(k, got - 1, 0.05) > 0.05)


def test_empty_and_single_trial_groups_do_not_break_the_grouped_statistics():
    rho = np.array([0.3, -0.1, 0.2])
    b = cs.robustness_stats_by_group(rho, np.array([0, 0, 2]), 3)
    assert b["n"].tolist() == [2, 0, 1]
    assert np.isnan(b["mean"][1])
    assert b["min"][0] == pytest.approx(-0.1)
    assert b["max"][0] == pytest.approx(0.3)
    assert b["min"][2] == b["max"][2] == pytest.approx(0.2)
    assert b["violated"][0] == pytest.approx(0.5)


def test_the_tool_writes_the_report_files_and_the_figure_pair(campaign, tmp_path):
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    r = subprocess.run([sys.executable, str(root / "datadriven" / "report.py"),
                        "--db", str(campaign["path"]), "--out", str(tmp_path)],
                       capture_output=True, text=True, env=env)
    assert r.returncode == 0, r.stderr

    doc = json.loads((tmp_path / "report.json").read_text())
    assert len(doc["groups"]) == 4
    assert doc["groups"][0]["trials"] == PER_GROUP
    assert "rho_quantile_dkw" in doc["groups"][0]

    csv_lines = (tmp_path / "report.csv").read_text().strip().splitlines()
    assert len(csv_lines) == 5                      # header plus one row per group
    assert csv_lines[0].startswith("design,environment,trials,failures,failure_rate")

    md = (tmp_path / "report.md").read_text()
    assert "| planner A | dense |" in md
    assert "Post-hoc robustness" in md

    for name in ("failure_rates.svg", "failure_rates.pdf"):
        assert (tmp_path / name).stat().st_size > 0
    assert (tmp_path / "failure_rates.svg").read_text().lstrip().startswith("<?xml")


def test_a_csv_campaign_groups_the_same_way(tmp_path):
    p = tmp_path / "campaign.csv"
    p.write_text("design_name,environment_name,state,robustness\n"
                 "A,sparse,TrialState.SUCCESSFUL|SHUT_DOWN,0.4\n"
                 "A,sparse,TrialState.ERRORED|SHUT_DOWN,-0.1\n"
                 "B,dense,TrialState.SUCCESSFUL|SHUT_DOWN,0.2\n")
    success, design, environment, rho = report.read_csv_campaign(str(p))
    s = report.summarise(success, design, environment, rho=rho)
    assert [" | ".join(g) for g in s["groups"]] == ["A | sparse", "B | dense"]
    assert s["trials"].tolist() == [2, 1]
    assert s["failures"].tolist() == [1, 0]


def test_a_bundle_payload_gives_up_its_named_number(tmp_path):
    """An experiment that relays several numbers in one payload, the shape a real campaign uses."""
    path = tmp_path / "bundle.db"
    con = sqlite3.connect(path)
    con.executescript(SCHEMA)
    con.execute("insert into design values (1,'d','demo',null,'[]')")
    con.execute("insert into environment values (1,'e','demo','{}',null)")
    con.execute("insert into experiment values (1,1,1,'demo')")
    con.executemany("insert into trial (id, state, experiment_id) values (?,?,1)",
                    [(1, "TrialState.SUCCESSFUL"), (2, "TrialState.SUCCESSFUL")])
    con.executemany('insert into "update" values (?,?,?,?)', [
        (1, 1, 0.0, json.dumps({"update": "metrics", "trial_id": 1,
                                "data": {"success_rate": 0.75, "time_to_goal": 58.4}})),
        (2, 2, 0.0, json.dumps({"update": "metrics", "trial_id": 2,
                                "data": {"success_rate": 1.0, "time_to_goal": 41.2}})),
    ])
    con.commit()
    con.close()
    assert pa.read_metric(str(path), [1, 2], name="success_rate").tolist() == [0.75, 1.0]
    assert pa.read_metric(str(path), [1, 2], name="time_to_goal").tolist() == [58.4, 41.2]
    assert np.all(np.isnan(pa.read_metric(str(path), [1, 2], name="not_in_the_bundle")))


def test_group_by_design_folds_the_environments_together(campaign):
    c = pa.read_campaign(str(campaign["path"]))
    per_pair = report.summarise(c["success"], c["design_name"], c["environment_name"])
    per_design = report.summarise(c["success"], c["design_name"], c["environment_name"],
                                  by="design")

    assert [" | ".join(g) for g in per_design["groups"]] == ["planner A | all", "planner B | all"]
    assert per_design["trials"].tolist() == [2 * PER_GROUP] * 2
    # the two pair groups of a design add up to that design's group
    assert per_design["failures"].tolist() == [
        int(per_pair["failures"][0] + per_pair["failures"][1]),
        int(per_pair["failures"][2] + per_pair["failures"][3])]

    per_environment = report.summarise(c["success"], c["design_name"], c["environment_name"],
                                       by="environment")
    assert [" | ".join(g) for g in per_environment["groups"]] == ["all | dense", "all | sparse"]
    assert per_environment["trials"].sum() == per_design["trials"].sum()


def test_a_metric_criterion_reproduces_the_recorded_outcome(campaign, tmp_path):
    """The fixture's state is `robustness >= 0`, so that criterion must give the same counts."""
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    r = subprocess.run([sys.executable, str(root / "datadriven" / "report.py"),
                        "--db", str(campaign["path"]), "--out", str(tmp_path),
                        "--failure-metric", "robustness", "--failure-below", "0.0"],
                       capture_output=True, text=True, env=env)
    assert r.returncode == 0, r.stderr
    assert "of " + str(PER_GROUP * MEANS.size) + " trials count as failures" in r.stdout

    doc = json.loads((tmp_path / "report.json").read_text())
    by_state = report.summarise(*report.read_database(str(campaign["path"]))[:3])
    assert [g["failures"] for g in doc["groups"]] == by_state["failures"].tolist()

    # a criterion needs a threshold
    r = subprocess.run([sys.executable, str(root / "datadriven" / "report.py"),
                        "--db", str(campaign["path"]), "--out", str(tmp_path),
                        "--failure-metric", "robustness"],
                       capture_output=True, text=True, env=env)
    assert r.returncode == 2
    assert "--failure-below" in r.stderr


def test_the_tag_narrows_the_read_to_one_campaign(campaign):
    kept = report.read_database(str(campaign["path"]), tag="demo")[0]
    assert kept.size == PER_GROUP * MEANS.size
    assert report.read_database(str(campaign["path"]), tag="some-other-campaign")[0].size == 0


def test_a_boolean_csv_column_reads_as_one_and_zero(tmp_path):
    p = tmp_path / "campaign.csv"
    p.write_text("trial_id,stuck,distance_m\n1,False,12.5\n2,True,3.2\n3,False,\n")
    assert report.read_csv_column(str(p), "stuck").tolist() == [0.0, 1.0, 0.0]
    d = report.read_csv_column(str(p), "distance_m")
    assert d[:2].tolist() == [12.5, 3.2]
    assert np.isnan(d[2])
