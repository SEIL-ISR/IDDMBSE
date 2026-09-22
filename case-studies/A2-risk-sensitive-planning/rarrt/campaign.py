"""The campaign: one planner run per (environment, noise level, policy, trial).

Each cell of the grid is what PERFECT would dispatch as a Design x Environment x
Trials job; here a multiprocessing pool stands in for the RQ workers so the case
study runs on one machine.  See the README for the mapping.
"""

import csv
import json
import multiprocessing as mp

import numpy as np

from rarrt.rrtstar import CostModel, plan, path_geometry, execute
from rarrt.world import make_world

FIELDS = ["env", "coverage", "sigma", "policy", "alpha", "run", "found",
          "nominal_length", "min_clearance", "planner_cost", "nodes", "plan_time",
          "realized_mean", "realized_p95", "realized_max", "over_budget", "hazard_rate"]


def run_trial(task):
    env, coverage, sigma, policy, alpha, run, cfg = task
    world = make_world(coverage, seed=run, half_width=cfg["half_width"])
    cost = CostModel(sigma=sigma, alpha=alpha, n_samples=cfg["n_samples"],
                     kappa=cfg["kappa"], d_hazard=cfg["d_hazard"],
                     p_max=cfg["p_max"], seed=cfg["crn_seed"] + run)
    result = plan(world, cost, iterations=cfg["iterations"], step=cfg["step"],
                  goal_bias=cfg["goal_bias"], seed=cfg["plan_seed"] + run)

    row = dict(env=env, coverage=coverage, sigma=sigma, policy=policy,
               alpha="" if alpha is None else alpha, run=run,
               found=int(result["path"] is not None), nominal_length="",
               min_clearance="", planner_cost="", nodes=result["nodes"],
               plan_time=result["plan_time"], realized_mean="", realized_p95="",
               realized_max="", over_budget="", hazard_rate="")
    if result["path"] is None:
        return row, np.empty(0)

    lengths, clearances = path_geometry(world, result["path"])
    rng = np.random.default_rng(cfg["exec_seed"] + run)
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
    return row, realized


def build_tasks(cfg):
    tasks = []
    for env, coverage in cfg["environments"]:
        for sigma in cfg["noise_levels"]:
            for policy, alpha in cfg["policies"]:
                for run in range(cfg["runs"]):
                    tasks.append((env, coverage, sigma, policy, alpha, run, cfg))
    return tasks


def run_campaign(cfg, processes=None, csv_path=None):
    """Run every task in a pool and return the rows plus per-cell aggregates."""
    tasks = build_tasks(cfg)
    processes = processes or min(mp.cpu_count(), 32)
    ctx = mp.get_context("fork")
    rows, pooled = [], {}
    with ctx.Pool(processes) as pool:
        for row, realized in pool.imap_unordered(run_trial, tasks, chunksize=4):
            rows.append(row)
            pooled.setdefault((row["env"], row["sigma"], row["policy"]), []).append(realized)
        pool.close()
        pool.join()

    rows.sort(key=lambda r: (r["env"], r["sigma"], str(r["alpha"]), r["run"]))
    if csv_path is not None:
        with open(csv_path, "w", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=FIELDS)
            writer.writeheader()
            writer.writerows(rows)
    return rows, summarise(rows, pooled, cfg)


def summarise(rows, pooled, cfg):
    """Per-cell aggregates.

    failure = an execution over the traversal budget, and every execution of a
    run whose planner returned no path.  worst-case path length = the 95th
    percentile of the realised traversal cost pooled over all executions of all
    successful runs in the cell.
    """
    def average(values):
        return float(np.mean(values)) if len(values) else float("nan")

    cells = []
    for key, chunks in sorted(pooled.items()):
        env, sigma, policy = key
        subset = [r for r in rows if (r["env"], r["sigma"], r["policy"]) == key]
        found = np.array([r["found"] for r in subset], dtype=bool)
        realized = np.concatenate([c for c in chunks if c.size]) if found.any() else np.empty(0)
        budget = cfg["budget_factor"] * cfg["straight_line"]
        missing = int((~found).sum()) * cfg["n_exec"]
        over = int((realized > budget).sum()) + missing
        lengths = np.array([r["nominal_length"] for r in subset if r["found"]], dtype=float)
        cells.append({
            "env": env, "sigma": sigma, "policy": policy,
            "alpha": subset[0]["alpha"],
            "runs": len(subset),
            "success_rate": float(found.mean()),
            "failure_rate": over / (len(subset) * cfg["n_exec"]),
            "hazard_rate": average([r["hazard_rate"] for r in subset if r["found"]]),
            "mean_path_length": float(lengths.mean()) if lengths.size else float("nan"),
            "worst_case_p95": float(np.quantile(realized, 0.95)) if realized.size else float("nan"),
            "worst_case_max": float(realized.max()) if realized.size else float("nan"),
            "mean_clearance": average([r["min_clearance"] for r in subset if r["found"]]),
            "mean_plan_time": average([r["plan_time"] for r in subset]),
        })
    return cells


def write_summary(path, cfg, cells):
    with open(path, "w") as handle:
        json.dump({"config": {k: v for k, v in cfg.items()}, "cells": cells}, handle, indent=2)
