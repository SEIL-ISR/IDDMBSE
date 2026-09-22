import pytest
import yaml

from tradesx import requirements as reqs


def test_the_file_holds_the_23_sysml_requirements():
    rq = reqs.load()
    assert len(rq) == 23
    assert len({r["id"] for r in rq}) == 23
    # the roll-ups and the two sensor-level requirements the model carries
    ids = {r["id"] for r in rq}
    assert {"Pr.1", "Pr.1.1", "Pr.1.2", "1", "2", "SH4"} <= ids
    assert {"P.1", "P.1.1", "P.1.2", "P.1.3", "P.1.4"} <= ids
    assert {"P.2", "P.2.1", "P.2.2", "P.2.3", "P.2.4"} <= ids


def test_partition_covers_every_requirement_exactly_once():
    rq = reqs.load()
    mb, dd = reqs.partition(rq)
    assert len(mb) + len(dd) == len(rq)
    assert not ({r["id"] for r in mb} & {r["id"] for r in dd})


def test_the_cost_requirements_are_model_based_and_the_run_metrics_are_not():
    rq = {r["id"]: r for r in reqs.load()}
    for rid in ["Pr.1", "Pr.1.1", "Pr.1.2", "1", "2"]:
        assert rq[rid]["class"] == "model-based"
    for rid in ["P.1.1", "P.1.2", "P.1.3", "P.2.1.1", "P.2.1.5", "P.2.2", "P.2.4"]:
        assert rq[rid]["class"] == "data-driven"


def test_every_requirement_has_a_reason():
    for r in reqs.load():
        assert isinstance(r["reason"], str) and r["reason"].strip()


def test_stage_grouping_partitions_the_list():
    rq = reqs.load()
    groups = reqs.by_stage(rq)
    assert sum(len(v) for v in groups.values()) == len(rq)
    assert set(groups) == set(reqs.STAGES)


def test_metric_map_only_names_the_four_local_metrics():
    m = reqs.metric_map()
    assert m
    assert set(m.values()) <= set(reqs.METRICS)


def test_table_has_one_line_per_requirement():
    rq = reqs.load()
    assert len(reqs.table(rq)) == len(rq)


def test_load_rejects_a_bad_class(tmp_path):
    bad = [{"id": "X", "name": "n", "text": "t", "class": "guesswork",
            "stage": "MBO", "metric": None, "reason": "r"}]
    p = tmp_path / "bad.yaml"
    p.write_text(yaml.safe_dump(bad))
    with pytest.raises(ValueError):
        reqs.load(p)


def test_load_rejects_a_duplicate_id(tmp_path):
    entry = {"id": "X", "name": "n", "text": "t", "class": "model-based",
             "stage": "MBO", "metric": None, "reason": "r"}
    p = tmp_path / "dup.yaml"
    p.write_text(yaml.safe_dump([entry, dict(entry)]))
    with pytest.raises(ValueError):
        reqs.load(p)
