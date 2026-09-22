"""The PERFECT campaign driver, replayed against a recording of a live server.

`tests/data/perfect_api_recording.json` was recorded while `tradesx.ddo_api`
drove a running PERFECT stack through a two-design, two-scenario campaign on
the `sensor-suite-sim` example: every request the driver made and the reply the
server gave, in order, split into the submission and the collection because
`GET /api/v1/experiments` answers differently before and after the trials run.
The replay server below answers from that recording and raises on a request the
recording does not hold, so a change to what the driver sends fails the test
rather than silently talking to nothing.

No test here starts or contacts a server.
"""

import importlib.util
import itertools
import json
import pathlib

import numpy as np
import pytest

from tradesx import ddo_api

RECORDING = pathlib.Path(__file__).parent / "data" / "perfect_api_recording.json"


class Replay:
    """Stands in for ddo_api.Server, answering from the recording."""

    def __init__(self, calls):
        self.calls = {}
        for c in calls:
            self.calls.setdefault(self._key(c["method"], c["path"], c.get("body")), []).append(c["reply"])
        self.sent = []

    @staticmethod
    def _key(method, path, body):
        return method, path, json.dumps(body, sort_keys=True)

    def _answer(self, method, path, body=None):
        self.sent.append((method, path, body))
        key = self._key(method, path, body)
        if key not in self.calls:
            raise AssertionError(f"the recording has no {method} {path} with this body: "
                                 f"{json.dumps(body, sort_keys=True)[:300]}")
        replies = self.calls[key]
        return replies[0] if len(replies) == 1 else replies.pop(0)

    def get(self, path):
        return self._answer("GET", path)

    def post(self, path, body):
        return self._answer("POST", path, body)


@pytest.fixture
def recording():
    if not RECORDING.exists():
        pytest.skip("no recording at " + str(RECORDING))
    return json.load(open(RECORDING))


@pytest.fixture
def submitting(recording):
    return Replay(recording["calls_submit"])


@pytest.fixture
def server(recording):
    return Replay(recording["calls_collect"])


# ------------------------------------------------------------------
# the driver against the recording

def test_submit_replays_against_the_recorded_server(submitting, recording):
    plan = recording["campaign"]
    ids = ddo_api.submit(submitting, recording["components"], plan["designs"],
                         (plan["template_name"], plan["template"]),
                         plan["environments"], plan["tag"])
    assert sorted(ids["designs"]) == sorted(plan["designs"])
    assert sorted(ids["environments"]) == sorted(plan["environments"])
    assert len(ids["experiments"]) == len(plan["designs"]) * len(plan["environments"])
    assert len(ids["trials"]) == len(ids["experiments"])


def test_a_second_submission_creates_no_second_experiment(server, recording):
    """Every pair already has an experiment in the collection recording.

    So create_experiments must post nothing and hand back the ids that are
    there. Any POST would fail, because the collection half of the recording
    holds none.
    """
    rows = server.get("/experiments")
    design_ids = sorted({r["design_id"] for r in rows})
    environment_ids = sorted({r["environment_id"] for r in rows})
    experiments, trials = ddo_api.create_experiments(
        server, design_ids, environment_ids, recording["campaign"]["tag"])
    assert trials == []
    assert experiments == sorted(r["id"] for r in rows)
    assert [m for m, _, _ in server.sent] == ["GET", "GET"]


def test_collect_reads_the_metrics_back(server, recording):
    rows = ddo_api.collect(server, recording["campaign"]["tag"])
    plan = recording["campaign"]
    assert len(rows) == len(plan["designs"]) * len(plan["environments"])
    assert {r["design"] for r in rows} == set(plan["designs"])
    assert {r["environment"] for r in rows} == set(plan["environments"])
    for r in rows:
        assert "SUCCESSFUL" in r["state"]
        assert 0.0 <= r["success_rate"] <= 1.0
        assert r["cost"] > 0.0


def test_collect_is_sorted_so_two_collections_agree(server, recording):
    rows = ddo_api.collect(server, recording["campaign"]["tag"])
    keys = [(r["design"], r["environment"], r["trial_id"]) for r in rows]
    assert keys == sorted(keys)


def test_progress_counts_only_this_tag(server, recording):
    done, total = ddo_api.progress(server, recording["campaign"]["tag"])
    assert done == total == len(recording["campaign"]["designs"]) * len(recording["campaign"]["environments"])
    assert ddo_api.progress(server, "not-a-tag") == (0, 0)


def test_an_unrecorded_request_is_an_error(server):
    with pytest.raises(AssertionError):
        server.get("/designs/9999")


# ------------------------------------------------------------------
# the table, the aggregate and the ranking

def rows_for(designs, environments, values):
    return [{"design": d, "environment": e, "trial_id": i, "m": values[i]}
            for i, (d, e) in enumerate((d, e) for d in designs for e in environments)]


def test_metric_table_places_every_row():
    designs = ["a", "b"]
    environments = ["x", "y", "z"]
    rows = rows_for(designs, environments, list(range(6)))
    table = ddo_api.metric_table(rows, designs, environments, ["m"])
    assert table.shape == (2, 3, 1)
    assert table[:, :, 0].tolist() == [[0.0, 1.0, 2.0], [3.0, 4.0, 5.0]]


def test_metric_table_leaves_a_missing_cell_as_nan():
    rows = rows_for(["a"], ["x", "y"], [1.0, 2.0])[:1]
    table = ddo_api.metric_table(rows, ["a"], ["x", "y"], ["m"])
    assert table[0, 0, 0] == 1.0
    assert np.isnan(table[0, 1, 0])


def test_metric_table_keeps_the_last_trial_of_a_cell():
    rows = [{"design": "a", "environment": "x", "trial_id": 1, "m": 5.0},
            {"design": "a", "environment": "x", "trial_id": 2, "m": 9.0}]
    table = ddo_api.metric_table(rows, ["a"], ["x"], ["m"])
    assert table[0, 0, 0] == 9.0


def test_aggregate_is_the_mean_over_scenarios():
    table = np.array([[[1.0, 10.0], [3.0, 20.0]], [[5.0, 30.0], [np.nan, 50.0]]])
    assert ddo_api.aggregate(table).tolist() == [[2.0, 15.0], [5.0, 40.0]]


def test_class_weights_split_by_the_requirement_counts():
    w_mbo, w_ddo = ddo_api.class_weights()
    assert w_mbo + w_ddo == pytest.approx(1.0)
    assert 0.0 < w_mbo < w_ddo


def test_stage_weights_sum_to_one_and_split_within_a_class():
    w = ddo_api.stage_weights(3, 6)
    assert w.sum() == pytest.approx(1.0)
    assert len(set(np.round(w[:3], 12))) == 1
    assert len(set(np.round(w[3:], 12))) == 1
    assert w[:3].sum() == pytest.approx(ddo_api.class_weights()[0])


def test_ranking_prefers_the_design_that_is_best_at_everything():
    mbo = np.array([[1.0, 1.0], [2.0, 2.0], [3.0, 3.0]])
    ddo = np.array([[9.0], [5.0], [1.0]])
    order, scores, mbo_order, mbo_scores = ddo_api.rank_designs(mbo, ddo, [-1, -1], [1])
    assert order[0] == 0 and order[-1] == 2
    assert mbo_order.tolist() == [0, 1, 2]
    assert scores[0] == pytest.approx(1.0)


def test_the_measured_attributes_can_overturn_the_model_based_ranking():
    # cheap but useless, against dear but able
    mbo = np.array([[1.0], [10.0]])
    ddo = np.array([[0.0], [1.0]])
    order, scores, mbo_order, _ = ddo_api.rank_designs(mbo, ddo, [-1], [1])
    assert mbo_order[0] == 0
    assert order[0] == 1


def test_weights_can_be_given_instead_of_derived():
    mbo = np.array([[1.0], [10.0]])
    ddo = np.array([[0.0], [1.0]])
    order, _, _, _ = ddo_api.rank_designs(mbo, ddo, [-1], [1], weights=[0.9, 0.1])
    assert order[0] == 0


# ------------------------------------------------------------------
# the campaign script's --out

CAMPAIGN_SCRIPT = (pathlib.Path(__file__).parents[1] / "case-studies" / "sensor-suite"
                   / "run_ddo_campaign.py")


def campaign_script():
    spec = importlib.util.spec_from_file_location("run_ddo_campaign", CAMPAIGN_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_campaign_script_writes_to_out_and_leaves_the_recorded_results(tmp_path, monkeypatch):
    """--collect --out puts the three tables and the three figures under the given
    directory; results/ and figures/, which hold the recorded campaign, are not
    written. The trials are made up, one per design and scenario."""
    C = campaign_script()
    pairs = list(itertools.product(sorted(C.campaign_designs()), sorted(C.campaign_environments())))
    rng = np.random.default_rng(0)
    values = rng.uniform(0.1, 1.0, size=(len(pairs), len(C.DDO_METRICS) + len(C.MBO_METRICS)))
    names = C.DDO_METRICS + C.MBO_METRICS
    rows = [dict({"design": d, "environment": e, "experiment_id": i + 1, "trial_id": i + 1,
                  "state": "TrialState.SUCCESSFUL|SHUT_DOWN", "wall_seconds": 1.0},
                 **dict(zip(names, v)))
            for i, ((d, e), v) in enumerate(zip(pairs, values.tolist()))]
    monkeypatch.setattr(C.ddo_api, "collect", lambda server, tag: rows)
    tracked = sorted(C.results.glob("*")) + sorted(C.figures.glob("ddo_*"))
    before = [p.stat().st_mtime_ns for p in tracked]

    out = tmp_path / "pipeline" / "sensor-suite"
    assert C.main(["--collect", "--out", str(out)]) == 0
    stems = ["ddo_success_heatmap", "ddo_mavf_ranking", "ddo_pareto_scatter"]
    assert sorted(p.name for p in out.iterdir()) == sorted(
        ["ddo_campaign.csv", "ddo_metrics.csv", "mavf_ddo_ranking.csv"]
        + [s + ".svg" for s in stems] + [s + ".pdf" for s in stems])
    assert len((out / "ddo_campaign.csv").read_text().splitlines()) == len(pairs) + 1
    assert [p.stat().st_mtime_ns for p in tracked] == before
