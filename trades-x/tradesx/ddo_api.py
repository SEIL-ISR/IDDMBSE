"""The data-driven stage: submit a campaign to a live PERFECT server, collect it, rank it.

`ddo.py` writes out the PERFECT command line for a campaign. This module runs
one instead, over PERFECT's JSON API at `/api/v1`, and reads the results back:

    library      POST /api/v1/component_implementations
    designs      POST /api/v1/designs
    scenarios    POST /api/v1/environment_templates, POST /api/v1/environments
    campaign     POST /api/v1/experiments          (creates and enqueues a trial)
    progress     GET  /api/v1/experiments
    results      GET  /api/v1/experiments/<id>, GET /api/v1/trials/<id>

Every create route is idempotent on the name, so re-running `submit` against a
database that already holds the campaign adds nothing and returns the ids that
are already there.

How a trial's numbers come back
-------------------------------
An experiment class reports what it measured with
`await self._relay_update("metrics", {...})`, which PERFECT stores as an
`Update` row on the trial. `GET /api/v1/trials/<id>` returns those rows, and
`trial_metrics` below picks the one named `metrics` out. Nothing here knows what
the metrics mean; the campaign script names the ones it wants.

The ranking
-----------
`aggregate` reduces the designs x environments x metrics table over the
environments, `mavf.rank` scores it. The weights come from the requirement
partition in `requirements.yaml`: the model-based requirements carry the
model-based attributes (a design's price, power and RAM, which are known from
the catalogue before anything runs) and the data-driven ones carry the measured
attributes, each class weighted by how many requirements it holds.

HTTP without a dependency: `urllib.request` from the standard library, since
nothing else in TRADES-X needs an HTTP client.
"""

import json
import time
import urllib.error
import urllib.request

import numpy as np

from tradesx import requirements
# tradesx/__init__.py re-exports the function `mavf`, so the module itself has
# to be reached by its full name.
from tradesx.mavf import rank as mavf_rank

DEFAULT_URL = "http://127.0.0.1:5001"


class Server:
    """The PERFECT JSON API at one base URL."""

    def __init__(self, url=DEFAULT_URL, timeout=30.0):
        self.base = url.rstrip("/") + "/api/v1"
        self.timeout = timeout

    def _call(self, path, body=None):
        url = self.base + path
        data = None
        headers = {}
        if body is not None:
            data = json.dumps(body).encode()
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(url, data=data, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                return json.loads(response.read().decode())
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"{path} returned {e.code}: {e.read().decode()[:400]}") from None

    def get(self, path):
        return self._call(path)

    def post(self, path, body):
        return self._call(path, body)


# ------------------------------------------------------------------
# building a campaign

def load_components(server, entries):
    """Put the sensor library in the database. Returns {name: id}."""
    reply = server.post("/component_implementations", {"components": entries})
    if reply["invalid"]:
        raise RuntimeError(f"PERFECT rejected {reply['invalid']}")
    return {c["name"]: c["id"] for c in reply["created"] + reply["existing"]}


def create_design(server, name, component_names, tag):
    reply = server.post("/designs", {
        "name": name, "tag": tag, "component_implementation_names": list(component_names),
    })
    return reply["design"]["id"]


def create_template(server, name, specification):
    reply = server.post("/environment_templates", {"name": name, "specification": specification})
    return reply["template"]["id"]


def create_environment(server, name, template_id, arguments, tag):
    reply = server.post("/environments", {
        "name": name, "tag": tag, "template_id": template_id, "arguments": arguments,
    })
    return reply["environment"]["id"]


def create_experiments(server, design_ids, environment_ids, tag, run=True, skip_existing=True):
    """One experiment per design and environment, each with a trial enqueued.

    POST /api/v1/experiments has no name to be idempotent on, so with
    `skip_existing` the pairs that already carry an experiment under this tag
    are left alone and only the missing ones are created. That is what makes a
    second submission of the same campaign add nothing instead of doubling it.
    """
    design_ids = list(design_ids)
    environment_ids = list(environment_ids)
    wanted = [(d, e) for d in design_ids for e in environment_ids]
    existing = {}
    if skip_existing:
        existing = {(x["design_id"], x["environment_id"]): x["id"]
                    for x in server.get("/experiments") if x["tag"] == tag}
    missing = [p for p in wanted if p not in existing]
    if not skip_existing or len(missing) == len(wanted):
        reply = server.post("/experiments", {
            "design_ids": design_ids, "environment_ids": environment_ids,
            "tag": tag, "run": run,
        })
        return reply["experiment_ids"], reply["trial_ids"]
    created, trials = [], []
    for design_id, environment_id in missing:
        reply = server.post("/experiments", {
            "design_ids": [design_id], "environment_ids": [environment_id],
            "tag": tag, "run": run,
        })
        created += reply["experiment_ids"]
        trials += reply["trial_ids"]
    return sorted(created + [existing[p] for p in wanted if p in existing]), trials


def submit(server, components, designs, template, environments, tag, run=True):
    """The whole campaign in one call.

    designs:      {design name: [component name, ...]}
    template:     (template name, template specification)
    environments: {environment name: {template argument: value}}
    """
    load_components(server, components)
    design_ids = {n: create_design(server, n, c, tag) for n, c in designs.items()}
    template_id = create_template(server, template[0], template[1])
    environment_ids = {n: create_environment(server, n, template_id, a, tag)
                       for n, a in environments.items()}
    experiment_ids, trial_ids = create_experiments(
        server, sorted(design_ids.values()), sorted(environment_ids.values()), tag, run)
    return {
        "designs": design_ids,
        "template": template_id,
        "environments": environment_ids,
        "experiments": experiment_ids,
        "trials": trial_ids,
    }


# ------------------------------------------------------------------
# watching it run

def progress(server, tag):
    """(finished, total) over the experiments carrying this tag."""
    rows = [e for e in server.get("/experiments") if e["tag"] == tag]
    done = sum(1 for e in rows if (e["last_trial_state"] or "").endswith("SHUT_DOWN"))
    return done, len(rows)


def wait(server, tag, timeout=1800.0, poll=5.0, report=None):
    """Block until every experiment with this tag has shut down, or time runs out.

    Returns (finished, total) as they stood when it gave up or finished. The
    loop is the campaign itself: it ends with the campaign and never outlives
    the process that started it.
    """
    deadline = time.monotonic() + timeout
    done, total = progress(server, tag)
    while done < total and time.monotonic() < deadline:
        time.sleep(poll)
        done, total = progress(server, tag)
        if report is not None:
            report(done, total)
    return done, total


# ------------------------------------------------------------------
# reading the results back

def trial_metrics(server, trial_id):
    """The dictionary an experiment relayed as `metrics`, or None."""
    trial = server.get(f"/trials/{trial_id}?updates=500")
    for update in reversed(trial["updates"]):
        data = update["data"]
        if isinstance(data, dict) and data.get("update") == "metrics":
            return data["data"]
    return None


def collect(server, tag):
    """One row per trial of the campaign, sorted so two collections agree.

    Each row carries the design name, the environment name, the trial id, the
    trial's terminal state, and every key the experiment reported.
    """
    rows = []
    for summary in server.get("/experiments"):
        if summary["tag"] != tag:
            continue
        experiment = server.get(f"/experiments/{summary['id']}")
        for trial in experiment["trials"]:
            metrics = trial_metrics(server, trial["id"])
            if metrics is None:
                continue
            row = {
                "design": experiment["design"]["name"],
                "environment": experiment["environment"]["name"],
                "experiment_id": experiment["id"],
                "trial_id": trial["id"],
                "state": trial["state"],
                "wall_seconds": trial["start_age"],
            }
            row.update(metrics)
            rows.append(row)
    rows.sort(key=lambda r: (r["design"], r["environment"], r["trial_id"]))
    return rows


def metric_table(rows, designs, environments, metric_names):
    """(designs, environments, metrics) table from the collected rows.

    Where an experiment ran more than one trial the last one wins, which is the
    order `collect` already sorted the rows into.
    """
    designs = list(designs)
    environments = list(environments)
    di = np.array([designs.index(r["design"]) for r in rows], dtype=int)
    ei = np.array([environments.index(r["environment"]) for r in rows], dtype=int)
    values = np.array([[r[m] for m in metric_names] for r in rows], dtype=float)
    table = np.full((len(designs), len(environments), len(metric_names)), np.nan)
    table[di, ei] = values
    return table


def aggregate(table):
    """Mean over the environments, ignoring cells no trial filled."""
    return np.nanmean(table, axis=1)


# ------------------------------------------------------------------
# the ranking

def class_weights(reqs=None):
    """How much each requirement class weighs, by how many requirements it holds."""
    model_based, data_driven = requirements.partition(reqs)
    total = len(model_based) + len(data_driven)
    return len(model_based) / total, len(data_driven) / total


def stage_weights(n_mbo, n_ddo, reqs=None):
    """Weights over [model-based attributes, data-driven attributes], summing to 1.

    Each class gets the share of the requirement list it holds, split equally
    among that class's attributes.
    """
    w_mbo, w_ddo = class_weights(reqs)
    return np.concatenate([np.full(n_mbo, w_mbo / n_mbo), np.full(n_ddo, w_ddo / n_ddo)])


def rank_designs(mbo, ddo, mbo_sense, ddo_sense, weights=None, reqs=None):
    """MAVF over the model-based and the measured attributes together.

    mbo: (n_designs, n_mbo)   the catalogue's numbers, known before anything runs
    ddo: (n_designs, n_ddo)   the campaign's numbers
    Returns (order, scores, mbo_order, mbo_scores): the joint ranking and, for
    comparison, the ranking the model-based attributes alone would give.
    """
    mbo = np.asarray(mbo, dtype=float)
    ddo = np.asarray(ddo, dtype=float)
    sense = np.concatenate([np.asarray(mbo_sense, float), np.asarray(ddo_sense, float)])
    if weights is None:
        weights = stage_weights(mbo.shape[1], ddo.shape[1], reqs)
    order, scores = mavf_rank(np.hstack([mbo, ddo]), weights, sense)
    mbo_weights = np.full(mbo.shape[1], 1.0 / mbo.shape[1])
    mbo_order, mbo_scores = mavf_rank(mbo, mbo_weights, mbo_sense)
    return order, scores, mbo_order, mbo_scores
