"""Failure-rate and robustness bounds over two campaigns, and a campaign database to report on.

First PERFECT's shipped dummy example, which has exactly one trial -- the bounds it gives are
degenerate and are printed to show what a one-trial campaign is worth.  Then a seeded
synthetic campaign of 200 trials with a known true failure probability, where the bounds can
be checked against the truth.  Finally a four-group campaign written out as a SQLite database
in PERFECT's own schema, under `datadriven/demo_out/`, so `report.py` can be run over it the
same way it is run over a database a real campaign left behind.
"""

import json
import os
import sqlite3
import sys

import numpy as np
from scipy import stats

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from campaign_stats import campaign_report, format_report  # noqa: E402
from perfect_adapter import read_campaign  # noqa: E402

repo = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
dummy_db = os.path.join(repo, "perfect", "examples", "dummy", "dummy.db")

# ------------------------------------------------------------------
# PERFECT's dummy example

c = read_campaign(dummy_db)
print("PERFECT dummy example: " + dummy_db)
print("designs " + str(sorted(set(c["design_name"]))) + ", states " + str(list(c["state"])))
print("wall-clock start_age " + str(np.round(c["start_age"], 3).tolist())
      + " s, sim_time " + str(c["sim_time"].tolist()))
print(format_report(campaign_report(c["success"], delta=0.05, target=0.05)))
print("one trial, zero failures: the point estimate is 0 and the exact upper bound is")
print("1 - 0.05**(1/1) = 0.95, i.e. this campaign rules out almost nothing. The line above")
print("says how many trials a zero-failure campaign needs before the bound reaches 0.05.")

# ------------------------------------------------------------------
# a synthetic campaign with a known truth

# each trial draws an STL robustness from N(0.15, 0.12) and fails exactly when it is negative,
# so the true failure probability is Phi(-0.15 / 0.12)
mu, sigma, n = 0.15, 0.12, 200
p_true = float(stats.norm.cdf(-mu / sigma))
rng = np.random.default_rng(20260922)
rho = rng.normal(mu, sigma, n)
success = rho >= 0

print()
print("synthetic campaign: " + str(n) + " trials, robustness ~ N(" + str(mu) + ", " + str(sigma)
      + "), failure iff robustness < 0")
print("true failure probability " + str(round(p_true, 5)))
print(format_report(campaign_report(success, rho=rho, delta=0.05, target=0.05)))
lo, hi = campaign_report(success, delta=0.05)["clopper_pearson"]
print("true rate inside the Clopper-Pearson interval: " + str(bool(lo <= p_true <= hi)))

# the same campaign ten times over, where the DKW band is finally narrower than the 5% level
rho = rng.normal(mu, sigma, 10 * n)
print()
print("the same campaign at " + str(10 * n) + " trials")
print(format_report(campaign_report(rho >= 0, rho=rho, delta=0.05, target=0.05)))

# ------------------------------------------------------------------
# a four-group campaign, written as a PERFECT database for report.py

# PERFECT's schema, transcribed from perfect/perfect/app/models.py: a trial belongs to an
# experiment, which pairs a design with an environment, and any per-trial number the runner
# reports arrives as a JSON payload in the `update` table.
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

designs = ["AGR + Dijkstra", "AGR + A-star"]
environments = ["range sparse", "range dense"]
per_group = 60

# mean robustness per (design, environment): the second planner is better, and both lose
# margin in the dense environment
means = np.array([[0.22, 0.12], [0.30, 0.20]])
rho_db = rng.normal(np.repeat(means.ravel(), per_group), sigma)
success_db = rho_db >= 0
experiment_of_trial = np.repeat(np.arange(1, means.size + 1), per_group)
state_db = np.where(success_db, "TrialState.SUCCESSFUL|SHUT_DOWN", "TrialState.ERRORED|SHUT_DOWN")
start_age_db = rng.uniform(10.0, 60.0, rho_db.size)

out_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "demo_out")
os.makedirs(out_dir, exist_ok=True)
db_path = os.path.join(out_dir, "campaign.db")
if os.path.exists(db_path):
    os.remove(db_path)
con = sqlite3.connect(db_path)
con.executescript(SCHEMA)
con.executemany("insert into design values (?,?,?,null,'[]')",
                [(i + 1, d, "demo") for i, d in enumerate(designs)])
con.executemany("insert into environment values (?,?,?,'{}',null)",
                [(i + 1, e, "demo") for i, e in enumerate(environments)])
con.executemany("insert into experiment values (?,?,?,'demo')",
                [(1 + i * len(environments) + j, i + 1, j + 1)
                 for i in range(len(designs)) for j in range(len(environments))])
trial_ids = np.arange(1, rho_db.size + 1)
con.executemany("insert into trial (id, state, start_age, experiment_id) values (?,?,?,?)",
                zip(trial_ids.tolist(), state_db.tolist(),
                    np.round(start_age_db, 3).tolist(), experiment_of_trial.tolist()))
con.executemany('insert into "update" (id, trial_id, timestamp, payload_json) values (?,?,?,?)',
                [(int(i), int(i), 0.0,
                  json.dumps({"update": "robustness", "trial_id": int(i), "data": float(r)}))
                 for i, r in zip(trial_ids, rho_db)])
con.commit()
con.close()

print()
print("wrote " + db_path + ": " + str(rho_db.size) + " trials over "
      + str(means.size) + " design/environment groups, "
      + str(int(np.count_nonzero(~success_db))) + " failures, each trial carrying a "
      + "robustness update")
print("report on it with:")
print("  uv run python datadriven/report.py --db datadriven/demo_out/campaign.db "
      "--out datadriven/demo_out")
