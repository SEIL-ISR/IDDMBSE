"""One risk-aware planner trial: plan under a risk functional, then execute the plan.

The planner is not in this file. It is the `rarrt` package of the
risk-sensitive-planning case study, and this script composes its pieces -- the
rock-field generator, the cost model, the RRT* search, the executor -- into the
single trial a PERFECT experiment dispatches. `RARRT_PACKAGE` says where that
package lives; without it the case study's directory in this repository is used.

The whole file is the mapping from two working files to one row of numbers:

    policy.yaml    what the design chose: the risk functional and its level
    scenario.yaml  what the environment chose: the rock field, the noise level,
                   the seed, and how many times the plan is executed

`experiment.py` runs this in a child process, so numpy and scipy do not have to
be installed in the Python environment that carries PERFECT:

    python planner_trial.py job.json metrics.json

`job.json` holds {"policy": ..., "scenario": ...} and `metrics.json` receives
the row that the trial reports back to the server.
"""

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_PACKAGE = os.path.normpath(os.path.join(
    HERE, os.pardir, os.pardir, os.pardir, "case-studies", "A2-risk-sensitive-planning"))
PACKAGE = os.environ.get("RARRT_PACKAGE") or DEFAULT_PACKAGE
if PACKAGE not in sys.path:
    sys.path.insert(0, PACKAGE)

import numpy as np

from rarrt.rrtstar import CostModel, plan, path_geometry, execute
from rarrt.world import make_world

# The columns of one row, in the order the case study's own campaign writes them.
FIELDS = ["env", "coverage", "sigma", "policy", "alpha", "run", "found",
          "nominal_length", "min_clearance", "planner_cost", "nodes", "plan_time",
          "realized_mean", "realized_p95", "realized_max", "over_budget", "hazard_rate"]

# The scenario keys that are the same in every cell of the campaign.
FIXED = ["iterations", "step", "goal_bias", "half_width", "n_samples", "kappa",
         "d_hazard", "p_max", "budget_factor", "crn_seed", "plan_seed", "exec_seed"]
COUNTS = ["iterations", "n_samples", "crn_seed", "plan_seed", "exec_seed"]


def settings(scenario, policy):
    """What one trial runs under, read out of the two working files.

    PERFECT's template substitution turns every numeric environment argument
    into a float, so the counts and the seeds are cast back to integers here.
    """
    cfg = {k: scenario[k] for k in FIXED}
    for k in COUNTS:
        cfg[k] = int(cfg[k])
    cfg["n_exec"] = int(scenario["n_exec"])
    name = scenario["environment"]
    return {
        "env": name,
        "coverage": float(scenario["coverages"][name]),
        "sigma": float(scenario["sigma"]),
        "seed": int(scenario["seed"]),
        "policy": policy["policy"],
        "alpha": None if policy["risk"] == "euclidean" else float(policy["alpha"]),
        "cfg": cfg,
    }


def run(scenario, policy):
    """Plan once and execute the plan `n_exec` times. -> row, executed costs, path.

    `alpha` of None is plain RRT*: the edge cost is the segment length. Any other
    value is RA-RRT*: the edge cost is CVaR at that level of the segment's cost
    distribution. Nothing else differs between the policies.
    """
    s = settings(scenario, policy)
    cfg, seed = s["cfg"], s["seed"]

    world = make_world(s["coverage"], seed=seed, half_width=cfg["half_width"])
    cost = CostModel(sigma=s["sigma"], alpha=s["alpha"], n_samples=cfg["n_samples"],
                     kappa=cfg["kappa"], d_hazard=cfg["d_hazard"],
                     p_max=cfg["p_max"], seed=cfg["crn_seed"] + seed)
    result = plan(world, cost, iterations=cfg["iterations"], step=cfg["step"],
                  goal_bias=cfg["goal_bias"], seed=cfg["plan_seed"] + seed)

    row = dict(env=s["env"], coverage=s["coverage"], sigma=s["sigma"],
               policy=s["policy"], alpha="" if s["alpha"] is None else s["alpha"],
               run=seed, found=int(result["path"] is not None), nominal_length="",
               min_clearance="", planner_cost="", nodes=result["nodes"],
               plan_time=result["plan_time"], realized_mean="", realized_p95="",
               realized_max="", over_budget="", hazard_rate="")
    if result["path"] is None:
        return row, np.empty(0), np.empty((0, 2))

    lengths, clearances = path_geometry(world, result["path"])
    rng = np.random.default_rng(cfg["exec_seed"] + seed)
    realized, hazard = execute(cost, lengths, clearances, cfg["n_exec"], rng)
    budget = cfg["budget_factor"] * float(np.linalg.norm(world.goal - world.start))

    row["nominal_length"] = float(lengths.sum())
    row["min_clearance"] = float(clearances.min())
    row["planner_cost"] = result["cost"]
    row["realized_mean"] = float(realized.mean())
    row["realized_p95"] = float(np.quantile(realized, 0.95))
    row["realized_max"] = float(realized.max())
    row["over_budget"] = float((realized > budget).mean())
    row["hazard_rate"] = float(hazard.mean())
    return row, realized, result["path"]


def metrics(scenario, policy):
    """The row plus the two arrays a campaign needs to aggregate cells.

    `executed` is every realised traversal cost, not a summary of them: the
    worst case of a cell is the 95th percentile over all executions of all its
    trials pooled, which cannot be recovered from per-trial percentiles. `path`
    is the planned polyline, which is what the paths figure draws.
    """
    row, executed, path = run(scenario, policy)
    out = dict(row)
    out["executed"] = executed.tolist()
    out["path"] = np.asarray(path).tolist()
    return out


def main():
    job = json.load(open(sys.argv[1]))
    out = metrics(job["scenario"], job["policy"])
    with open(sys.argv[2], "w") as f:
        json.dump(out, f)
    print(out["policy"], out["env"], "sigma", out["sigma"], "seed", out["run"],
          "found", out["found"], "plan", round(out["plan_time"], 2), "s")


if __name__ == "__main__":
    main()
