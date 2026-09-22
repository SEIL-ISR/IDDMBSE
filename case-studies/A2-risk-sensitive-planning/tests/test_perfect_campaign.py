"""The PERFECT campaign driver, without a server.

Every function tested here is pure: the grid it submits and the tables it builds
out of collected trials. The trials themselves are made up in `collected()`
below, in exactly the shape `tradesx.ddo_api.collect` returns them.
"""

import csv

import numpy as np
import pytest

import run_perfect_campaign as R

FIELDS_SET = set(R.FIELDS)


def collected(seed=0):
    """Rows in the shape a collection off a live server returns."""
    rng = np.random.default_rng(seed)
    rows = []
    trial = 1
    for policy in R.policies():
        for env, coverage in R.ENVIRONMENTS:
            for sigma in R.SIGMAS:
                for run in R.SEEDS:
                    executed = 80.0 + 20.0 * coverage + rng.gamma(2.0, 8.0, size=16)
                    rows.append({
                        "design": policy,
                        "environment": env + "-sigma" + str(sigma) + "-seed" + str(run),
                        "experiment_id": trial, "trial_id": trial,
                        "state": "TrialState.SUCCESSFUL|SHUT_DOWN", "wall_seconds": 1.0,
                        "env": env, "coverage": coverage, "sigma": sigma,
                        "policy": policy, "alpha": "", "run": run, "found": 1,
                        "nominal_length": 82.0, "min_clearance": 0.7,
                        "planner_cost": 82.0, "nodes": 1300, "plan_time": 0.5,
                        "realized_mean": float(executed.mean()),
                        "realized_p95": float(np.quantile(executed, 0.95)),
                        "realized_max": float(executed.max()),
                        "over_budget": float((executed > 118.79).mean()),
                        "hazard_rate": 0.3,
                        "executed": executed.tolist(),
                        "path": [[-28.0, -28.0], [0.0, 0.0], [28.0, 28.0]],
                    })
                    trial += 1
    return rows


def test_the_grid_is_every_policy_against_every_environment():
    designs = R.campaign_designs()
    environments = R.campaign_environments()
    assert len(designs) == 5
    assert len(environments) == len(R.ENVIRONMENTS) * len(R.SIGMAS) * len(R.SEEDS)
    assert len(designs) * len(environments) == 300
    for name, components in designs.items():
        assert components == [name]


def test_each_environment_carries_the_four_template_arguments():
    for key, arguments in R.campaign_environments().items():
        assert sorted(arguments) == ["environment", "n_exec", "seed", "sigma"]
        assert key.startswith(arguments["environment"])
        assert arguments["n_exec"] == R.N_EXEC
        assert arguments["sigma"] in R.SIGMAS
        assert arguments["seed"] in R.SEEDS
    assert len({tuple(sorted(a.items())) for a in R.campaign_environments().values()}) == 60


def test_the_collected_trials_become_one_cell_per_policy_and_noise_level():
    rows = collected()
    cfg = R.cell_config(R.scenario_defaults())
    cells = R.summarise(R.campaign_rows(rows), R.pooled_executions(rows), cfg)
    assert len(cells) == len(R.ENVIRONMENTS) * len(R.SIGMAS) * len(R.policies())
    for c in cells:
        assert c["runs"] == len(R.SEEDS)
        assert c["success_rate"] == 1.0
        assert 0.0 <= c["failure_rate"] <= 1.0
        assert c["worst_case_p95"] <= c["worst_case_max"]


def test_the_cell_worst_case_pools_every_execution_of_the_cell():
    rows = collected()
    cfg = R.cell_config(R.scenario_defaults())
    cells = R.summarise(R.campaign_rows(rows), R.pooled_executions(rows), cfg)
    c = cells[0]
    key = (c["env"], c["sigma"], c["policy"])
    pooled = np.concatenate([np.array(r["executed"]) for r in rows
                             if (r["env"], r["sigma"], r["policy"]) == key])
    assert c["worst_case_p95"] == pytest.approx(np.quantile(pooled, 0.95))
    assert c["worst_case_max"] == pytest.approx(pooled.max())


def test_the_campaign_table_holds_every_case_study_column(tmp_path):
    rows = collected()
    path = tmp_path / "campaign.csv"
    R.write_campaign(rows, path)
    with open(path) as f:
        table = list(csv.reader(f))
    assert table[0][6:] == R.FIELDS
    assert len(table) == len(rows) + 1
    assert all(len(r) == len(table[0]) for r in table)


def test_two_writes_of_the_same_collection_are_byte_identical(tmp_path):
    rows = collected()
    first, second = tmp_path / "a.csv", tmp_path / "b.csv"
    R.write_campaign(rows, first)
    R.write_campaign(rows, second)
    assert first.read_bytes() == second.read_bytes()

    cfg = R.cell_config(R.scenario_defaults())
    cells = R.summarise(R.campaign_rows(rows), R.pooled_executions(rows), cfg)
    R.write_cells(cells, first)
    R.write_cells(cells, second)
    assert first.read_bytes() == second.read_bytes()


def test_every_trial_carries_the_two_numbers_a_safety_report_reads():
    """`over_budget` decides the outcome of a trial and `hazard_rate` is the
    number summarised beside it, so both have to be plain floats on every row."""
    for r in collected():
        assert isinstance(r["over_budget"], float) and 0.0 <= r["over_budget"] <= 1.0
        assert isinstance(r["hazard_rate"], float) and 0.0 <= r["hazard_rate"] <= 1.0
    assert "over_budget" in FIELDS_SET and "hazard_rate" in FIELDS_SET


def test_the_budget_is_the_one_the_example_scenario_sets():
    cfg = R.cell_config(R.scenario_defaults())
    assert cfg["straight_line"] == pytest.approx(np.hypot(56.0, 56.0))
    assert cfg["budget_factor"] == R.scenario_defaults()["budget_factor"]
    assert cfg["n_exec"] == R.N_EXEC
