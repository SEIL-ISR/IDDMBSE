"""Turn a PERFECT campaign into the arrays `campaign_stats` wants.

PERFECT records one row per trial in the `trial` table of its SQLite database, joined to
`experiment` and through it to `design` and `environment`.  This module reads that database
(always read-only) and hands back parallel numpy arrays.

Schema as it actually is, read from `perfect/perfect/app/models.py` and confirmed against
`perfect/examples/dummy/dummy.db`:

* `trial.state` is a plain string column, not an enum column.  The runner sends an integer
  bitmask of `perfect.experiment.experiment.TrialState`, which is an `enum.Flag`, and
  `perfect/perfect/app/tasks.py` stores `str(TrialState(mask))`.  Python's `Flag.__str__`
  joins the set members with `|`, so a finished successful trial reads
  `TrialState.SUCCESSFUL|SHUT_DOWN`.  A trial counts as a success exactly when `SUCCESSFUL`
  is one of those members.
* There is **no** `duration` column.  The two time columns are `start_age` (wall-clock
  seconds the trial ran, `time.time() - start`) and `sim_time` (simulated seconds off the
  `/clock` topic; it is NULL in the dummy example).
* `trial.experiment_id -> experiment.id`, `experiment.design_id -> design.id`,
  `experiment.environment_id -> environment.id`.
* per-trial numbers other than the two times arrive as rows of the `update` table, one JSON
  payload each: the runner sends `{"update": <name>, "trial_id": n, "data": <value>}` and
  `Trial.add_update` (`perfect/perfect/app/models.py`) stores it verbatim.  `read_metric`
  pulls one named number back out of that stream.
"""

import csv
import json
import sqlite3

import numpy as np

SUCCESS_FLAG = "SUCCESSFUL"

QUERY = """
select t.id, t.state, t.start_age, t.sim_time, e.id, e.tag, d.id, d.name, d.tag, v.id, v.name, v.tag
from trial t
join experiment e on t.experiment_id = e.id
join design d on e.design_id = d.id
join environment v on e.environment_id = v.id
order by t.id
"""


def _columns(rows):
    return list(zip(*rows)) if rows else [()] * 12


def _as_float(col):
    return np.array([np.nan if v is None else float(v) for v in col], dtype=float)


def succeeded(states):
    """Vectorised state-string test: True where the stored flag set contains SUCCESSFUL."""
    s = np.array(["" if v is None else str(v) for v in states], dtype=object).astype(str)
    return np.char.find(s, SUCCESS_FLAG) >= 0


def read_campaign(db_path, design=None, experiment_tag=None):
    """Read a PERFECT database into arrays. `db_path` is opened read-only and never written.

    `design` filters on the design name, `experiment_tag` on the experiment tag; both optional.
    Returns a dict of equal-length arrays: trial_id, state, success, start_age, sim_time,
    experiment_id, experiment_tag, design_id, design_name, design_tag.
    """
    con = sqlite3.connect("file:" + str(db_path) + "?mode=ro", uri=True)
    try:
        rows = con.execute(QUERY).fetchall()
    finally:
        con.close()
    c = _columns(rows)
    out = {
        "trial_id": np.array(c[0], dtype=np.int64),
        "state": np.array([("" if v is None else str(v)) for v in c[1]], dtype=object),
        "success": succeeded(c[1]),
        "start_age": _as_float(c[2]),
        "sim_time": _as_float(c[3]),
        "experiment_id": np.array(c[4], dtype=np.int64),
        "experiment_tag": np.array([("" if v is None else str(v)) for v in c[5]], dtype=object),
        "design_id": np.array(c[6], dtype=np.int64),
        "design_name": np.array([("" if v is None else str(v)) for v in c[7]], dtype=object),
        "design_tag": np.array([("" if v is None else str(v)) for v in c[8]], dtype=object),
        "environment_id": np.array(c[9], dtype=np.int64),
        "environment_name": np.array([("" if v is None else str(v)) for v in c[10]], dtype=object),
        "environment_tag": np.array([("" if v is None else str(v)) for v in c[11]], dtype=object),
    }
    keep = np.ones(out["trial_id"].size, dtype=bool)
    if design is not None:
        keep &= out["design_name"].astype(str) == design
    if experiment_tag is not None:
        keep &= out["experiment_tag"].astype(str) == experiment_tag
    return {k: v[keep] for k, v in out.items()}


def read_metric(db_path, trial_ids, name="robustness"):
    """One named number per trial out of the `update` table, aligned to `trial_ids`.

    A payload counts if it is `{"update": name, ..., "data": value}` (the shape PERFECT's
    runner sends) or if it simply has `name` as a key.  The last matching payload of a trial
    wins, so a metric written repeatedly during a run reports its final value.  Trials with no
    such payload -- and databases with no `update` table at all -- come back as nan.
    """
    trial_ids = np.asarray(trial_ids, dtype=np.int64)
    values = {}
    con = sqlite3.connect("file:" + str(db_path) + "?mode=ro", uri=True)
    try:
        has_updates = con.execute(
            "select count(*) from sqlite_master where type='table' and name='update'"
        ).fetchone()[0]
        rows = con.execute('select trial_id, payload_json from "update" order by id').fetchall() \
            if has_updates else []
    finally:
        con.close()
    for trial_id, payload in rows:
        try:
            d = json.loads(payload)
        except (TypeError, ValueError):
            continue
        if not isinstance(d, dict):
            continue
        if d.get("update") == name and "data" in d:
            v = d["data"]
        elif name in d:
            v = d[name]
        else:
            continue
        try:
            values[int(trial_id)] = float(v)
        except (TypeError, ValueError):
            continue
    if not values:
        return np.full(trial_ids.size, np.nan)
    keys = np.array(sorted(values), dtype=np.int64)
    vals = np.array([values[k] for k in keys], dtype=float)
    idx = np.searchsorted(keys, trial_ids)
    idx = np.clip(idx, 0, keys.size - 1)
    out = np.where(keys[idx] == trial_ids, vals[idx], np.nan)
    return out


def read_campaign_csv(path, state_column="state", robustness_column="robustness"):
    """CSV fallback for a campaign exported from somewhere other than the live database.

    The file needs a header row; `state_column` holds the same kind of state string PERFECT
    writes (the test is the same one: does the string contain SUCCESSFUL), and
    `robustness_column` is optional.  `design_name` and `environment_name` columns are carried
    through when they are there, so a CSV campaign groups the same way a database one does.
    """
    with open(path, newline="") as f:
        rows = list(csv.DictReader(f))
    states = [r.get(state_column) for r in rows]
    out = {"state": np.array([("" if v is None else str(v)) for v in states], dtype=object),
           "success": succeeded(states)}
    if rows and robustness_column in rows[0]:
        out["robustness"] = np.array([float(r[robustness_column]) for r in rows], dtype=float)
    for col in ("design_name", "environment_name"):
        if rows and col in rows[0]:
            out[col] = np.array([str(r[col]) for r in rows], dtype=object)
    return out
