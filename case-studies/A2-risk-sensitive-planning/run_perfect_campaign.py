# The same comparison as run_case_study.py, run as a PERFECT campaign: the
# planner is the design variable, one design per policy, one environment per
# rock field and noise level and seed, one trial each.
#
#   python run_perfect_campaign.py --submit --url http://127.0.0.1:5001
#   python run_perfect_campaign.py --collect
#
# --submit loads the five planner implementations, creates the designs, the
# environment template and the environments, then creates one experiment per
# design and environment with a trial enqueued, and waits for them. --collect
# reads the trials back through the same API, writes the campaign table and the
# per-cell aggregates, and draws the three figures from them.
#
# The PERFECT example behind it is perfect/examples/rarrt-planning, whose
# components.json is the planner library this script loads and whose
# scenario.yaml holds the settings every cell shares.

import argparse
import csv
import json
import pathlib
import sys

import numpy as np
import yaml
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

here = pathlib.Path(__file__).parent
example = here / ".." / ".." / "perfect" / "examples" / "rarrt-planning"
tradesx_path = here / ".." / ".." / "trades-x"
if str(tradesx_path) not in sys.path:
    sys.path.insert(0, str(tradesx_path))

from tradesx import ddo_api                                    # noqa: E402

from rarrt.campaign import FIELDS, summarise, write_summary    # noqa: E402
from rarrt.rrtstar import path_geometry                        # noqa: E402
from rarrt.world import make_world                             # noqa: E402

results = here / "results" / "perfect"
figures = here / "figures"

TAG = "rarrt"

# The grid. Five seeds per cell rather than the fifty the standalone campaign
# runs, because one PERFECT runner takes the trials one at a time.
ENVIRONMENTS = [("easy", 0.08), ("medium", 0.16), ("hard", 0.26)]
SIGMAS = [0.01, 0.05, 0.1, 0.5]
SEEDS = [0, 1, 2, 3, 4]
N_EXEC = 400

POLICY_COLOUR = {"rrtstar": "#444444", "neutral": "#1f77b4", "cvar0.1": "#2ca02c",
                 "cvar0.5": "#ff7f0e", "cvar0.9": "#d62728"}
PATH_POLICIES = ["rrtstar", "neutral", "cvar0.9"]


def library():
    return json.load(open(example / "components.json"))


def policies():
    return [c["name"] for c in library()]


def scenario_defaults():
    return yaml.safe_load(open(example / "scenario.yaml"))


def campaign_designs():
    """One design per policy, each over that policy's planner implementation."""
    return {name: [name] for name in policies()}


def campaign_environments():
    """One environment per rock field, noise level and seed."""
    grid = {}
    for name, _ in ENVIRONMENTS:
        for sigma in SIGMAS:
            for seed in SEEDS:
                key = name + "-sigma" + str(sigma) + "-seed" + str(seed)
                grid[key] = {"environment": name, "sigma": sigma,
                             "seed": seed, "n_exec": N_EXEC}
    return grid


# ------------------------------------------------------------------
# submit

def do_submit(server, wait_seconds):
    designs = campaign_designs()
    environments = campaign_environments()
    template = json.load(open(example / "environment_template.json"))[0]

    print("policies:", len(designs), "environments:", len(environments),
          "trials:", len(designs) * len(environments))
    ids = ddo_api.submit(server, library(), designs,
                         (template["name"], template["specification"]),
                         environments, TAG)
    print("experiments:", len(ids["experiments"]),
          "trials enqueued:", len(ids["trials"]))

    seen = [-1]

    def report(done, total):
        if done != seen[0]:
            seen[0] = done
            print("  ", done, "/", total, "shut down")

    done, total = ddo_api.wait(server, TAG, timeout=wait_seconds, poll=5.0, report=report)
    print("finished:", done, "of", total)
    return done == total


# ------------------------------------------------------------------
# collect

def fmt(v):
    # numpy scalars repr themselves as np.float64(...), so everything numeric is
    # coerced to a plain Python number first. Rounding to nine places keeps two
    # collections of the same database byte-identical.
    if v is None or v == "":
        return ""
    if isinstance(v, (float, np.floating)):
        return repr(round(float(v), 9))
    if isinstance(v, (int, np.integer)):
        return str(int(v))
    return v


def campaign_rows(rows):
    """The per-run rows the case study's own aggregation takes, out of the trials."""
    return [{f: r[f] for f in FIELDS} for r in rows]


def pooled_executions(rows):
    """{(environment, sigma, policy): [executed costs, ...]} for the cell aggregates."""
    pooled = {}
    for r in rows:
        key = (r["env"], r["sigma"], r["policy"])
        pooled.setdefault(key, []).append(np.asarray(r["executed"], dtype=float))
    return pooled


def cell_config(defaults):
    """The grid, plus the two numbers the per-cell aggregation needs.

    `budget_factor` and `straight_line` set the traversal budget a failure is
    measured against, and `n_exec` says how many executions each trial pooled.
    """
    world = make_world(ENVIRONMENTS[0][1], seed=0, half_width=defaults["half_width"])
    cfg = {k: defaults[k] for k in ("iterations", "step", "goal_bias", "half_width",
                                    "n_samples", "kappa", "d_hazard", "p_max",
                                    "budget_factor", "crn_seed", "plan_seed", "exec_seed")}
    cfg["environments"] = [list(e) for e in ENVIRONMENTS]
    cfg["noise_levels"] = SIGMAS
    cfg["policies"] = policies()
    cfg["seeds"] = SEEDS
    cfg["n_exec"] = N_EXEC
    cfg["straight_line"] = float(np.linalg.norm(world.goal - world.start))
    return cfg


def write_campaign(rows, path):
    columns = ["design", "environment", "experiment_id", "trial_id", "state",
               "wall_seconds"] + FIELDS
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(columns)
        for r in rows:
            w.writerow([fmt(r.get(c)) for c in columns])


def write_cells(cells, path):
    columns = ["env", "sigma", "policy", "alpha", "runs", "success_rate", "failure_rate",
               "hazard_rate", "mean_path_length", "worst_case_p95", "worst_case_max",
               "mean_clearance", "mean_plan_time"]
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(columns)
        for c in cells:
            w.writerow([fmt(c[k]) for k in columns])


def do_collect(server):
    results.mkdir(parents=True, exist_ok=True)
    figures.mkdir(exist_ok=True)
    defaults = scenario_defaults()

    rows = ddo_api.collect(server, TAG)
    states = sorted({r["state"] for r in rows})
    successful = [r for r in rows if "SUCCESSFUL" in (r["state"] or "")]
    print("trials collected:", len(rows), "states:", states)
    print("SUCCESSFUL trials:", len(successful))
    print("planner found a path in", sum(r["found"] for r in rows), "of", len(rows))

    write_campaign(rows, results / "campaign.csv")
    cfg = cell_config(defaults)
    cells = summarise(campaign_rows(rows), pooled_executions(rows), cfg)
    write_cells(cells, results / "cells.csv")
    write_summary(results / "summary.json", cfg, cells)

    print_table(cells, cfg)
    draw_paths(rows, defaults)
    draw_failure_and_worstcase(cells)
    draw_premium_against_protection(cells)
    print()
    print("results written to", results.relative_to(here))
    print("figures written to", figures.relative_to(here))
    return len(successful), cells


def cell(cells, env, sigma, policy):
    return next(c for c in cells
                if (c["env"], c["sigma"], c["policy"]) == (env, sigma, policy))


def print_table(cells, cfg):
    print()
    print("over budget above", round(cfg["budget_factor"] * cfg["straight_line"], 1), "m")
    print("env     sigma  policy    success  failure  hazard  mean len  worst p95"
          "   max   clearance  plan s")
    for name, _ in ENVIRONMENTS:
        for sigma in SIGMAS:
            for policy in policies():
                c = cell(cells, name, sigma, policy)
                print(name.ljust(7), str(sigma).rjust(5), " ", policy.ljust(9),
                      str(round(c["success_rate"], 3)).rjust(6),
                      str(round(c["failure_rate"], 4)).rjust(8),
                      str(round(c["hazard_rate"], 3)).rjust(7),
                      str(round(c["mean_path_length"], 1)).rjust(8),
                      str(round(c["worst_case_p95"], 1)).rjust(10),
                      str(round(c["worst_case_max"], 1)).rjust(7),
                      str(round(c["mean_clearance"], 2)).rjust(8),
                      str(round(c["mean_plan_time"], 2)).rjust(8))


# ------------------------------------------------------------------
# figures

def save(fig, stem):
    fig.savefig(figures / (stem + ".svg"))
    fig.savefig(figures / (stem + ".pdf"))
    plt.close(fig)


def draw_paths(rows, defaults):
    """The planned paths of three policies, as the trials reported them.

    The rock field is the one the seed defines, so it is redrawn here; the
    polylines are the ones the campaign's own trials planned and are read out of
    the trial results.
    """
    sigma = SIGMAS[-1]
    seed = SEEDS[0]
    by_key = {(r["policy"], r["env"], r["sigma"], r["run"]): r for r in rows}

    fig, axes = plt.subplots(1, 3, figsize=(12.6, 4.6), constrained_layout=True)
    for ax, (name, coverage) in zip(axes, ENVIRONMENTS):
        world = make_world(coverage, seed=seed, half_width=defaults["half_width"])
        circles = [plt.Circle(c, r, color="0.15", zorder=1)
                   for c, r in zip(world.centers, world.radii)]
        for c in circles:
            ax.add_patch(c)
        for policy in PATH_POLICIES:
            r = by_key.get((policy, name, sigma, seed))
            if r is None or not r["found"]:
                continue
            path = np.asarray(r["path"])
            lengths, clearances = path_geometry(world, path)
            ax.plot(path[:, 0], path[:, 1], color=POLICY_COLOUR[policy], linewidth=2.0,
                    zorder=3, label=policy + "  len " + str(round(lengths.sum(), 1))
                    + ", clr " + str(round(clearances.min(), 2)))
        ax.plot(*world.start, "o", color="#00a000", markersize=8, zorder=4)
        ax.plot(*world.goal, "*", color="#d62728", markersize=14, zorder=4)
        ax.set_xlim(-defaults["half_width"], defaults["half_width"])
        ax.set_ylim(-defaults["half_width"], defaults["half_width"])
        ax.set_aspect("equal")
        ax.set_title(name + " environment")
        ax.set_xlabel("x [m]")
        ax.legend(loc="lower right", fontsize=7, framealpha=0.9)
    axes[0].set_ylabel("y [m]")
    fig.suptitle("Planned paths the campaign's trials returned, noise level "
                 + str(sigma) + ", seed " + str(seed))
    save(fig, "perfect_paths_by_environment")


def draw_failure_and_worstcase(cells):
    fig, axes = plt.subplots(2, 3, figsize=(12.0, 6.4), sharex=True,
                             constrained_layout=True)
    for column, (name, _) in enumerate(ENVIRONMENTS):
        for policy in policies():
            picked = [cell(cells, name, s, policy) for s in SIGMAS]
            axes[0, column].plot(SIGMAS, [c["failure_rate"] for c in picked], "o-",
                                 color=POLICY_COLOUR[policy], label=policy)
            axes[1, column].plot(SIGMAS, [c["worst_case_p95"] for c in picked], "o-",
                                 color=POLICY_COLOUR[policy], label=policy)
        axes[0, column].set_title(name + " environment")
        axes[1, column].set_xlabel("noise level sigma")
        axes[1, column].set_xscale("log")
    axes[0, 0].set_ylabel("failure rate")
    axes[1, 0].set_ylabel("worst-case path length [m], p95")
    axes[0, 0].legend(fontsize=8)
    save(fig, "perfect_failure_and_worstcase")


def draw_premium_against_protection(cells):
    sigma = SIGMAS[-1]
    fig, axes = plt.subplots(1, 3, figsize=(12.0, 4.0), constrained_layout=True)
    for ax, (name, _) in zip(axes, ENVIRONMENTS):
        for policy in policies():
            c = cell(cells, name, sigma, policy)
            ax.plot(c["mean_path_length"], c["worst_case_p95"], "o",
                    color=POLICY_COLOUR[policy], markersize=9, label=policy)
        ax.set_title(name + " environment")
        ax.set_xlabel("mean planned path length [m]")
        ax.margins(0.18)
    axes[0].set_ylabel("worst-case path length [m], p95")
    axes[0].legend(fontsize=8)
    fig.suptitle("premium against protection, noise level " + str(sigma))
    save(fig, "perfect_premium_against_protection")


# ------------------------------------------------------------------

def main(argv=None):
    p = argparse.ArgumentParser(description="the risk-sensitive planning campaign on PERFECT")
    p.add_argument("--url", default=ddo_api.DEFAULT_URL, help="the PERFECT server")
    p.add_argument("--submit", action="store_true", help="create and run the campaign")
    p.add_argument("--collect", action="store_true", help="read it back, tabulate and draw")
    p.add_argument("--wait", type=float, default=2400.0, help="seconds to wait for the trials")
    args = p.parse_args(argv)
    if not (args.submit or args.collect):
        p.error("give --submit, --collect, or both")

    server = ddo_api.Server(args.url)
    if args.submit:
        do_submit(server, args.wait)
    if args.collect:
        do_collect(server)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
