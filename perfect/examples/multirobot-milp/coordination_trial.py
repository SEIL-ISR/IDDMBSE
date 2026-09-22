"""One coordination trial: synthesise the fleet's joint plan, execute it once under
the environment's disturbance, score each robot's executed trace, and write the
verdicts back into the fleet model.

The synthesis and the scoring are not in this file. They are the `assured_ma`
package of the assured multi-robot coordination case study, and this script
composes its pieces into the single trial a PERFECT experiment dispatches, in the
order of the case study's own chain:

    model/fleet_requirements.yaml -> per-robot reach-avoid STL (specs.load_fleet)
    -> big-M MILP solved by HiGHS (synth.synthesise)
    -> execution under the tracking-error process (execute.execute)
    -> quantitative STL robustness per robot (robustness.rho, robustness.explain)
    -> goal-satisfaction write-back (writeback.write_model)

`MULTIROBOT_PACKAGE` says where that package lives; without it the case study's
directory in this repository is used. The whole file is the mapping from the
working files to one row of numbers:

    config.yaml     what the design chose: the station allocation, the required
                    robustness margin, and the solver's stopping rule
    execution.yaml  what the environment chose: the disturbance level and seed
    agr_fleet.yaml  the trial's own copy of the fleet model, which it writes into

`experiment.py` runs this in a child process, so numpy and scipy do not have to be
installed in the Python environment that carries PERFECT:

    python coordination_trial.py job.json metrics.json

`job.json` holds {"config": ..., "execution": ..., "fleet": <path>, "model": <path>}
and `metrics.json` receives what the trial reports back to the server.
"""

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_PACKAGE = os.path.normpath(os.path.join(
    HERE, os.pardir, os.pardir, os.pardir, "case-studies", "B3-assured-multi-robot"))
PACKAGE = os.environ.get("MULTIROBOT_PACKAGE") or DEFAULT_PACKAGE
if PACKAGE not in sys.path:
    sys.path.insert(0, PACKAGE)

import numpy as np
import yaml

from assured_ma import encode, execute, specs, synth, writeback
from assured_ma import robustness as rb

FLEET = os.path.join(PACKAGE, "model", "fleet_requirements.yaml")
MODEL = os.path.join(PACKAGE, "model", "agr_fleet.yaml")


def settings(config, execution, robot_ids):
    """What one trial runs under, read out of the two working files.

    PERFECT's template substitution turns every numeric environment argument into
    a float, so the seed comes back as an integer here. The allocation is a mapping
    from robot id to the index of the station pair it is given, so that PERFECT's
    file update can write each entry on its own (it appends to a list instead of
    replacing it).
    """
    node_limit = config.get("node_limit")
    return {
        "allocation": tuple(int(config["allocation"][r]) for r in robot_ids),
        "required_margin": float(config["required_margin"]),
        "node_limit": None if node_limit is None else int(node_limit),
        "mip_rel_gap": float(config["mip_rel_gap"]),
        "time_limit_s": float(config["time_limit_s"]),
        "sigma": float(execution["sigma"]),
        "seed": int(execution["seed"]),
        "pole": float(execution["pole"]),
        "clip_sigma": float(execution["clip_sigma"]),
    }


def make_problem(cfg, starts, required):
    """The MILP data of the model file, as the case study's run builds it."""
    ws = cfg["workspace"]
    return encode.Problem(N=cfg["horizon"]["steps"], dt=cfg["horizon"]["dt"],
                          v_max=cfg["dynamics"]["v_max"], a_max=cfg["dynamics"]["a_max"],
                          ws_lo=np.array([ws["x"][0], ws["y"][0]], float),
                          ws_hi=np.array([ws["x"][1], ws["y"][1]], float),
                          starts=starts, rho_cap=cfg["synthesis"]["rho_cap"],
                          effort_weight=cfg["synthesis"]["effort_weight"],
                          rho_required=required)


def stop_reason(status, message):
    """Why the search ended, in one word or two.

    scipy reports HiGHS's node limit as status 4 with the message "Solution limit
    reached", and a wall-clock stop as status 1.
    """
    if status == 0:
        return "optimal"
    if status == 2:
        return "infeasible"
    if "Solution limit" in message:
        return "node limit"
    if "Time limit" in message:
        return "time limit"
    return message


def rounded(a):
    return np.round(np.asarray(a, float), 6).tolist()


def run(config, execution, fleet_path=FLEET, model_path=MODEL):
    """Synthesise, execute once, score, write back. -> the trial's metrics."""
    robot_ids = [r["id"] for r in yaml.safe_load(open(fleet_path))["robots"]]
    s = settings(config, execution, robot_ids)
    fleet = specs.load_fleet(fleet_path, allocation=s["allocation"])
    cfg = fleet["cfg"]
    prob = make_problem(cfg, fleet["starts"], s["required_margin"])
    out = synth.synthesise(prob, fleet["specs"], mip_rel_gap=s["mip_rel_gap"],
                           time_limit=s["time_limit_s"], node_limit=s["node_limit"])

    m = {
        "robots": robot_ids,
        "allocation": list(s["allocation"]),
        "stations": [[g.name for g, _ in goals] for goals in fleet["goal_sets"]],
        "required_margin": s["required_margin"],
        "sigma": s["sigma"], "seed": s["seed"], "pole": s["pole"],
        "clip_sigma": s["clip_sigma"],
        "node_limit": s["node_limit"], "mip_rel_gap_target": s["mip_rel_gap"],
        "time_limit_s": s["time_limit_s"],
        "n_var": out["n_var"], "n_bin": out["n_bin"], "n_con": out["n_con"],
        "nnz": out["nnz"],
        "mip_status": out["status"], "mip_message": out["message"],
        "stop": stop_reason(out["status"], out["message"]),
        "mip_gap": out["mip_gap"], "dual_bound": out["dual_bound"],
        "nodes": out["nodes"], "solve_wall": out["wall_s"],
        "feasible": "plan" in out,
        "effort": None, "dense_margin": None,
        "planned_rho": None, "planned_min_rho": None,
        "executed_rho": None, "min_rho": None, "violations": None,
        "verdicts": None, "binding": None, "goal_satisfaction": None,
        "plan": None, "executed": None,
    }
    if "plan" not in out:
        return m

    plan = out["plan"]
    executed = execute.execute(plan, s["pole"], s["sigma"], s["clip_sigma"], s["seed"])[0]
    planned_rho = np.array([rb.rho(phi, plan) for phi in fleet["specs"]])
    executed_rho = np.array([rb.rho(phi, executed) for phi in fleet["specs"]])
    binding = [rb.explain(phi, executed)[1] for phi in fleet["specs"]]
    verdicts = ["satisfied" if v > 0 else "violated" for v in executed_rho]

    writeback.write_model(model_path, {
        r: {"rho": float(executed_rho[i]), "verdict": verdicts[i], "binding": binding[i]}
        for i, r in enumerate(robot_ids)})
    written = writeback.read_goal_satisfaction(model_path)

    m.update({
        "effort": float(np.abs(out["acc"]).sum()),
        "dense_margin": rb.dense_obstacle_margin(plan, fleet["obstacles"]),
        "planned_rho": planned_rho.tolist(),
        "planned_min_rho": float(planned_rho.min()),
        "executed_rho": executed_rho.tolist(),
        "min_rho": float(executed_rho.min()),
        "violations": int((executed_rho < 0).sum()),
        "verdicts": verdicts,
        "binding": binding,
        "goal_satisfaction": [written[r] for r in robot_ids],
        "plan": rounded(plan),
        "executed": rounded(executed),
    })
    return m


def main():
    job = json.load(open(sys.argv[1]))
    out = run(job["config"], job["execution"], job["fleet"], job["model"])
    with open(sys.argv[2], "w") as f:
        json.dump(out, f)
    print("allocation", out["allocation"], "margin", out["required_margin"],
          "sigma", out["sigma"], "seed", out["seed"], "stop", out["stop"],
          "nodes", out["nodes"], "solve", round(out["solve_wall"], 1), "s",
          "min rho", None if out["min_rho"] is None else round(out["min_rho"], 4))


if __name__ == "__main__":
    main()
