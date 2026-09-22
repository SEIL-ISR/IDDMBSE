"""The trial against the coordination package's own functions, on a tiny fleet.

`coordination_trial.run` composes `assured_ma`'s pieces into one trial. Every
number it relays has to be the number those pieces give when called directly, or
a campaign run through PERFECT would not be measuring what the case study
measures. The fleet here is two robots on a 4 m square with one pillar, so the
MILP solves in a fraction of a second; the case study's own three-robot fleet
takes about a minute per solve and is what the campaign runs.
"""

import shutil

import numpy as np
import pytest
import yaml

import coordination_trial as ct
from assured_ma import execute, specs, synth, writeback
from assured_ma import robustness as rb

FLEET = """
workspace: {x: [0.0, 4.0], y: [0.0, 4.0]}
horizon: {steps: 8, dt: 0.5}
dynamics: {model: double_integrator, v_max: 1.0, a_max: 1.5}
separation: {d_min: 0.5, norm: inf}
synthesis: {rho_cap: 1.0, effort_weight: 0.001}
obstacles:
  - {id: OBS_PILLAR, type: box, x: [1.6, 2.4], y: [1.6, 2.4]}
robots:
  - id: AGR_1
    start: [0.5, 3.5]
    goals:
      - {id: ST_A, x: [3.0, 3.8], y: [3.0, 3.8], window: [5, 8]}
  - id: AGR_2
    start: [0.5, 0.5]
    goals:
      - {id: ST_B, x: [3.0, 3.8], y: [0.2, 1.0], window: [5, 8]}
"""

MODEL = """# a two-robot fleet model for the tests
model: tiny
blocks:
- id: AGR_1
  kind: part
- id: AGR_2
  kind: part
"""


@pytest.fixture
def files(tmp_path):
    fleet = tmp_path / "fleet.yaml"
    model = tmp_path / "agr_fleet.yaml"
    fleet.write_text(FLEET)
    model.write_text(MODEL)
    return str(fleet), str(model)


def config(allocation, margin):
    return {"allocation": {"AGR_1": allocation[0], "AGR_2": allocation[1]},
            "required_margin": margin, "node_limit": 500, "mip_rel_gap": 0.0,
            "time_limit_s": 60.0}


EXECUTION = {"sigma": 0.09, "seed": 3, "pole": 0.8, "clip_sigma": 3.0}


def reference(fleet_path, allocation, margin, execution):
    """The same chain, called piece by piece."""
    fleet = specs.load_fleet(fleet_path, allocation=allocation)
    prob = ct.make_problem(fleet["cfg"], fleet["starts"], margin)
    out = synth.synthesise(prob, fleet["specs"], mip_rel_gap=0.0, time_limit=60.0,
                           node_limit=500)
    executed = execute.execute(out["plan"], execution["pole"], execution["sigma"],
                               execution["clip_sigma"], int(execution["seed"]))[0]
    return fleet, out, executed


@pytest.mark.parametrize("allocation", [(0, 1), (1, 0)])
def test_the_relayed_numbers_are_the_packages_own(files, allocation):
    fleet_path, model_path = files
    m = ct.run(config(allocation, 0.1), EXECUTION, fleet_path, model_path)
    fleet, out, executed = reference(fleet_path, allocation, 0.1, EXECUTION)

    assert m["feasible"] and m["stop"] == "optimal"
    assert np.allclose(m["plan"], np.round(out["plan"], 6))
    assert np.allclose(m["executed"], np.round(executed, 6))
    planned = [rb.rho(phi, out["plan"]) for phi in fleet["specs"]]
    scored = [rb.rho(phi, executed) for phi in fleet["specs"]]
    assert m["planned_rho"] == pytest.approx(planned, abs=1e-12)
    assert m["executed_rho"] == pytest.approx(scored, abs=1e-12)
    assert m["min_rho"] == pytest.approx(min(scored), abs=1e-12)
    assert m["violations"] == sum(v < 0 for v in scored)
    assert m["binding"] == [rb.explain(phi, executed)[1] for phi in fleet["specs"]]
    assert m["effort"] == pytest.approx(np.abs(out["acc"]).sum(), abs=1e-9)
    assert m["dense_margin"] == pytest.approx(
        rb.dense_obstacle_margin(out["plan"], fleet["obstacles"]), abs=1e-12)
    assert m["n_var"] == out["n_var"] and m["n_bin"] == out["n_bin"]


def test_the_plan_holds_the_required_margin_and_the_execution_spends_it(files):
    fleet_path, model_path = files
    m = ct.run(config((0, 1), 0.1), EXECUTION, fleet_path, model_path)
    assert min(m["planned_rho"]) >= 0.1 - 1e-6
    assert m["planned_min_rho"] == pytest.approx(min(m["planned_rho"]))
    assert m["executed_rho"] != pytest.approx(m["planned_rho"])


def test_the_verdicts_are_written_into_the_trials_model_copy(files):
    fleet_path, model_path = files
    m = ct.run(config((1, 0), 0.1), EXECUTION, fleet_path, model_path)
    written = writeback.read_goal_satisfaction(model_path)
    assert [written["AGR_1"], written["AGR_2"]] == m["goal_satisfaction"]
    assert m["goal_satisfaction"] == pytest.approx(m["executed_rho"], abs=1e-6)
    blocks = {b["id"]: b for b in yaml.safe_load(open(model_path))["blocks"]}
    assert [blocks[r]["verdict"] for r in ("AGR_1", "AGR_2")] == m["verdicts"]
    assert open(model_path).read().startswith("# a two-robot fleet model")


def test_the_allocation_gives_each_robot_the_other_robots_stations(files):
    fleet_path, model_path = files
    straight = ct.run(config((0, 1), 0.1), EXECUTION, fleet_path, model_path)
    swapped = ct.run(config((1, 0), 0.1), EXECUTION, fleet_path, model_path)
    assert straight["stations"] == [["ST_A"], ["ST_B"]]
    assert swapped["stations"] == [["ST_B"], ["ST_A"]]
    assert swapped["allocation"] == [1, 0]
    # swapped, the two paths cross, and the shared separation conjunct is what binds
    assert swapped["binding"][0].startswith("sep(1,2)")
    assert swapped["executed_rho"][0] == swapped["executed_rho"][1]


def test_a_margin_the_map_cannot_afford_reports_no_plan(files):
    fleet_path, model_path = files
    m = ct.run(config((0, 1), 0.45), EXECUTION, fleet_path, model_path)
    assert m["stop"] == "infeasible" and not m["feasible"]
    for k in ("min_rho", "executed_rho", "planned_rho", "violations", "plan", "effort"):
        assert m[k] is None
    assert open(model_path).read() == MODEL


def test_the_seed_survives_the_templates_float_substitution(files):
    fleet_path, model_path = files
    as_float = dict(EXECUTION, seed=3.0, sigma=0.09)
    a = ct.run(config((0, 1), 0.1), as_float, fleet_path, model_path)
    b = ct.run(config((0, 1), 0.1), EXECUTION, fleet_path, model_path)
    assert a["seed"] == 3 and isinstance(a["seed"], int)
    assert a["executed"] == b["executed"]
    c = ct.run(config((0, 1), 0.1), dict(EXECUTION, seed=4), fleet_path, model_path)
    assert c["executed"] != b["executed"]


def test_the_stop_reasons():
    assert ct.stop_reason(0, "Optimization terminated successfully.") == "optimal"
    assert ct.stop_reason(2, "The problem is infeasible.") == "infeasible"
    assert ct.stop_reason(4, "(HiGHS Status 16: Solution limit reached)") == "node limit"
    assert ct.stop_reason(1, "Time limit reached. (HiGHS Status 13: Time limit reached)") \
        == "time limit"


def test_the_shipped_fleet_builds_the_case_studys_problem():
    s = ct.settings(yaml.safe_load(open(ct.HERE + "/config.yaml")),
                    yaml.safe_load(open(ct.HERE + "/execution.yaml")),
                    ["AGR_1", "AGR_2", "AGR_3"])
    fleet = specs.load_fleet(ct.FLEET, allocation=s["allocation"])
    prob = ct.make_problem(fleet["cfg"], fleet["starts"], s["required_margin"])
    assert (prob.N, prob.dt, prob.v_max, prob.a_max) == (16, 0.9, 0.9, 1.0)
    assert prob.rho_required == 0.35 and prob.R == 3
    assert np.array_equal(prob.ws_hi, [8.0, 6.0])
