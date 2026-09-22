"""The trial against the case study's own campaign function.

`planner_trial.run` composes the `rarrt` package's pieces into one trial.
`rarrt.campaign.run_trial` composes the same pieces into the same trial for the
standalone case study. The two have to produce the same row for the same inputs,
or a campaign run through PERFECT would not be measuring what the case study
measures; the first test here is that comparison, field by field.
"""

import numpy as np
import pytest
import yaml

import planner_trial as pt
from rarrt.campaign import run_trial

HERE = pt.HERE


def scenario(**over):
    """The shipped scenario, made small enough to run several times in a test."""
    s = yaml.safe_load(open(HERE + "/scenario.yaml"))
    s.update(iterations=300, n_samples=128, n_exec=50)
    s.update(over)
    return s


def policy(name, risk, alpha):
    return {"policy": name, "risk": risk, "alpha": alpha}


POLICIES = [policy("rrtstar", "euclidean", 0.0), policy("neutral", "cvar", 0.0),
            policy("cvar0.9", "cvar", 0.9)]


@pytest.mark.parametrize("p", POLICIES, ids=[p["policy"] for p in POLICIES])
@pytest.mark.parametrize("env", ["easy", "hard"])
def test_the_trial_is_the_case_studys_own_trial(p, env):
    s = scenario(environment=env, sigma=0.5, seed=2)
    settings = pt.settings(s, p)
    task = (settings["env"], settings["coverage"], settings["sigma"],
            settings["policy"], settings["alpha"], settings["seed"], settings["cfg"])
    reference, reference_executed = run_trial(task)
    row, executed, _ = pt.run(s, p)

    # plan_time is a wall clock and differs between two runs of the same plan
    for field in pt.FIELDS:
        if field != "plan_time":
            assert row[field] == reference[field], field
    assert np.array_equal(executed, reference_executed)


def test_the_relayed_metrics_summarise_the_executions_they_carry():
    s = scenario(environment="medium", sigma=0.5, seed=1)
    m = pt.metrics(s, policy("cvar0.5", "cvar", 0.5))
    executed = np.array(m["executed"])
    assert executed.size == 50
    assert m["realized_mean"] == pytest.approx(executed.mean())
    assert m["realized_p95"] == pytest.approx(np.quantile(executed, 0.95))
    assert m["realized_max"] == pytest.approx(executed.max())
    budget = s["budget_factor"] * np.hypot(56.0, 56.0)
    assert m["over_budget"] == pytest.approx((executed > budget).mean())


def test_the_relayed_path_is_the_one_the_lengths_were_taken_from():
    s = scenario(environment="medium", sigma=0.1, seed=3)
    m = pt.metrics(s, policy("cvar0.1", "cvar", 0.1))
    path = np.array(m["path"])
    assert path.shape[1] == 2
    segments = np.linalg.norm(np.diff(path, axis=0), axis=1)
    assert segments.sum() == pytest.approx(m["nominal_length"])
    assert path[0] == pytest.approx([-28.0, -28.0])
    assert path[-1] == pytest.approx([28.0, 28.0])


def test_plain_rrtstar_costs_a_path_its_own_length():
    """With no risk functional the edge cost is the segment length, so the
    planner's cost-to-come at the goal is the path length itself."""
    s = scenario(environment="easy", sigma=0.5, seed=0)
    row, _, _ = pt.run(s, policy("rrtstar", "euclidean", 0.0))
    assert row["planner_cost"] == pytest.approx(row["nominal_length"])

    row, _, _ = pt.run(s, policy("cvar0.9", "cvar", 0.9))
    assert row["planner_cost"] > row["nominal_length"]


def test_the_counts_survive_the_templates_float_substitution():
    """PERFECT fills a template argument with float(value) where it can, so a
    seed arrives as 3.0 and a count as 400.0. Both have to come back as ints."""
    s = scenario(environment="hard", sigma=0.5, seed=3.0, n_exec=50.0)
    settings = pt.settings(s, policy("neutral", "cvar", 0.0))
    assert settings["seed"] == 3 and isinstance(settings["seed"], int)
    assert settings["cfg"]["n_exec"] == 50 and isinstance(settings["cfg"]["n_exec"], int)
    assert settings["coverage"] == 0.26
    assert settings["alpha"] == 0.0


def test_the_euclidean_risk_setting_is_the_only_one_without_a_level():
    s = scenario()
    assert pt.settings(s, policy("rrtstar", "euclidean", 0.7))["alpha"] is None
    assert pt.settings(s, policy("cvar0.5", "cvar", 0.5))["alpha"] == 0.5
