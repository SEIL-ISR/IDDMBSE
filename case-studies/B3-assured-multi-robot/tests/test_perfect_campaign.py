"""The PERFECT campaign driver, without a server.

Every function tested here is pure: the grid it submits and the tables it builds
out of collected trials. The trials themselves are made up in `collected()` below,
in exactly the shape `tradesx.ddo_api.collect` returns them: the fields the
example's trial relays, plus the design, environment, ids, state and wall time.
"""

import csv
import json

import numpy as np
import pytest

import run_perfect_campaign as R


def trial(design, sigma, seed, trial_id, rng):
    allocation, margin = R.parse_design(design)
    row = {"design": design, "environment": R.environment_name(sigma, seed),
           "experiment_id": trial_id, "trial_id": trial_id,
           "state": "TrialState.SUCCESSFUL|SHUT_DOWN", "wall_seconds": 1.0,
           "robots": R.ROBOTS, "allocation": list(allocation), "required_margin": margin,
           "sigma": sigma, "seed": seed, "pole": 0.8, "clip_sigma": 3.0,
           "n_var": 1841, "n_bin": 1043, "n_con": 2390, "nnz": 7988}
    if margin >= 0.5:
        row.update({"mip_status": 2, "mip_message": "The problem is infeasible.",
                    "stop": "infeasible", "mip_gap": None, "dual_bound": None,
                    "nodes": None, "solve_wall": 0.01, "feasible": False})
        for k in ("effort", "dense_margin", "planned_rho", "planned_min_rho", "executed_rho",
                  "min_rho", "violations", "verdicts", "binding", "goal_satisfaction",
                  "plan", "executed"):
            row[k] = None
        return row
    # the plan depends on the design only; the execution on the environment as well
    plan = np.random.default_rng(sum(allocation) * 7 + int(margin * 100)).uniform(0, 6, (3, 17, 2))
    executed = plan + rng.normal(0.0, sigma, plan.shape)
    rho = margin - 4.0 * sigma * rng.uniform(0.0, 1.5, 3)
    row.update({"mip_status": 4, "mip_message": "(HiGHS Status 16: Solution limit reached)",
                "stop": "node limit", "mip_gap": 0.4 + margin, "dual_bound": 3.0,
                "nodes": 8000, "solve_wall": 50.0 + 10 * margin + seed, "feasible": True,
                "effort": 5.0 + 10 * margin + sum(allocation[:1]), "dense_margin": 0.1,
                "planned_rho": [margin] * 3, "planned_min_rho": margin,
                "executed_rho": rho.tolist(), "min_rho": float(rho.min()),
                "violations": int((rho < 0).sum()),
                "verdicts": ["satisfied" if v > 0 else "violated" for v in rho],
                "binding": ["sep(1,2)@k=8", "sep(1,2)@k=8", "OBS_WALL_SOUTH@k=6"],
                "goal_satisfaction": np.round(rho, 6).tolist(),
                "plan": np.round(plan, 6).tolist(), "executed": np.round(executed, 6).tolist()})
    return row


def collected(seed=0):
    rng = np.random.default_rng(seed)
    rows = []
    k = 1
    for design in R.design_names():
        for sigma in R.SIGMAS:
            for s in R.SEEDS:
                rows.append(trial(design, sigma, s, k, rng))
                k += 1
    rows.sort(key=lambda r: (r["design"], r["environment"], r["trial_id"]))
    return rows


def test_the_grid_is_every_configuration_against_every_disturbance():
    designs = R.campaign_designs()
    environments = R.campaign_environments()
    assert len(designs) == 24 and len(environments) == 9
    assert list(designs) == [c["name"] for c in R.library()]
    for name, components in designs.items():
        assert components == [name]
    for name, arguments in environments.items():
        assert sorted(arguments) == ["seed", "sigma"]
        assert name == R.environment_name(arguments["sigma"], arguments["seed"])
    assert {a["sigma"] for a in environments.values()} == set(R.SIGMAS)


def test_a_design_name_is_its_allocation_and_its_margin():
    assert R.parse_design("alloc102-m0.35") == ((1, 0, 2), 0.35)
    assert R.parse_design("alloc012-m0.5") == ((0, 1, 2), 0.5)
    assert sorted({R.parse_design(n)[1] for n in R.design_names()}) == R.MARGINS


def test_the_campaign_table_has_one_row_per_trial_and_every_robot(tmp_path):
    rows = collected()
    path = tmp_path / "campaign.csv"
    R.write_table([R.flat(r) for r in rows], R.CAMPAIGN_COLUMNS, path)
    table = list(csv.DictReader(open(path)))
    assert len(table) == len(rows) == 216
    first = table[0]
    assert first["allocation"] == "0-1-2" and first["required_margin"] == "0.15"
    assert first["executed_rho_AGR_3"] == repr(round(rows[0]["executed_rho"][2], 9))
    infeasible = [t for t in table if t["required_margin"] == "0.5"]
    assert len(infeasible) == 54
    assert all(t["feasible"] == "0" and t["min_rho"] == "" for t in infeasible)


def test_the_design_table_counts_what_the_trials_report():
    rows = collected()
    designs = {d["design"]: d for d in R.design_table(rows)}
    d = designs["alloc120-m0.35"]
    trials = [r for r in rows if r["design"] == "alloc120-m0.35"]
    mins = np.array([r["min_rho"] for r in trials])
    assert d["trials"] == d["feasible_trials"] == 9
    assert d["worst_min_rho"] == pytest.approx(mins.min())
    assert d["mean_min_rho"] == pytest.approx(mins.mean())
    assert d["violating_trials"] == int((mins < 0).sum())
    rho = np.array([r["executed_rho"] for r in trials])
    assert [d["violations_" + r] for r in R.ROBOTS] == list((rho < 0).sum(axis=0))
    assert d["distinct_plans"] == 1
    assert designs["alloc120-m0.5"]["feasible_trials"] == 0
    assert "rank" not in designs["alloc120-m0.5"]


def test_the_ranking_puts_the_best_worst_case_first():
    designs = [d for d in R.design_table(collected()) if "rank" in d]
    ranked = sorted(designs, key=lambda d: d["rank"])
    worst = [d["worst_min_rho"] for d in ranked]
    assert worst == sorted(worst, reverse=True)
    assert [d["rank"] for d in ranked] == list(range(1, 19))


def test_a_design_whose_trials_disagree_is_counted():
    rows = collected()
    for r in rows:
        if r["design"] == "alloc012-m0.15" and r["seed"] == 2:
            r["plan"] = (np.array(r["plan"]) + 0.5).tolist()
    d = next(d for d in R.design_table(rows) if d["design"] == "alloc012-m0.15")
    assert d["distinct_plans"] == 2


def test_the_cells_and_the_margins_pool_the_right_trials():
    rows = collected()
    cells = R.cell_table(rows)
    assert len(cells) == 24 * 3
    c = next(c for c in cells if c["design"] == "alloc021-m0.45" and c["sigma"] == 0.12)
    mins = [r["min_rho"] for r in rows if r["design"] == "alloc021-m0.45" and r["sigma"] == 0.12]
    assert c["trials"] == 3 and c["worst_min_rho"] == pytest.approx(min(mins))
    margins = {m["required_margin"]: m for m in R.margin_table(rows)}
    assert margins[0.5]["feasible_designs"] == 0 and "violation_rate" not in margins[0.5]
    pooled = [r["min_rho"] for r in rows if r["required_margin"] == 0.15]
    assert margins[0.15]["trials"] == 54
    assert margins[0.15]["violating_trials"] == sum(v < 0 for v in pooled)


def test_the_binding_conjunct_kinds():
    assert R.binding_kind("sep(1,2)@k=8") == "separation"
    assert R.binding_kind("OBS_PILLAR@k=3") == "obstacle"
    assert R.binding_kind("ST_N1@k=10") == "station"
    counts = R.violated_conjuncts(collected())
    assert sum(counts.values()) == sum(r["violations"] for r in collected() if r["feasible"])


def test_two_collections_of_the_same_trials_write_the_same_bytes(tmp_path):
    rows = collected()
    designs = R.design_table(rows)
    margins = R.margin_table(rows)
    for name in ("a", "b"):
        R.write_table([R.flat(r) for r in rows], R.CAMPAIGN_COLUMNS, tmp_path / (name + ".csv"))
        R.write_table(designs, R.DESIGN_COLUMNS, tmp_path / (name + "-d.csv"))
        with open(tmp_path / (name + ".json"), "w") as f:
            json.dump(R.summarise(rows, designs, margins), f, indent=1)
    for suffix in (".csv", "-d.csv", ".json"):
        assert (tmp_path / ("a" + suffix)).read_bytes() == (tmp_path / ("b" + suffix)).read_bytes()


def test_out_sends_the_tables_and_the_figures_there(tmp_path, monkeypatch):
    """--collect --out writes everything under the given directory and nothing in
    results/perfect or figures/, which hold the recorded campaign."""
    rows = collected()
    monkeypatch.setattr(R.ddo_api, "collect", lambda server, tag: rows)
    monkeypatch.setattr(R, "results", R.results)
    monkeypatch.setattr(R, "figures", R.figures)
    out = tmp_path / "multirobot"
    assert R.main(["--collect", "--out", str(out)]) == 0
    stems = ["perfect_min_rho", "perfect_solve", "perfect_violations", "perfect_trajectories"]
    assert sorted(p.name for p in out.iterdir()) == sorted(
        ["campaign.csv", "designs.csv", "cells.csv", "summary.json"]
        + [s + ".svg" for s in stems] + [s + ".pdf" for s in stems])
    summary = json.load(open(out / "summary.json"))
    assert summary["trials"] == 216 and summary["feasible_trials"] == 162
    assert summary["top"]["design"] == summary["ranking"][0]
    assert len(summary["top"]["executed"]) == 9
