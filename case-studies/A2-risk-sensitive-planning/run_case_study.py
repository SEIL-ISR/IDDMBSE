import os

os.environ.setdefault("OMP_NUM_THREADS", "1")

import pathlib
import time

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import yaml
from matplotlib.collections import LineCollection

from rarrt.campaign import run_campaign, write_summary
from rarrt.rrtstar import CostModel, plan, path_geometry
from rarrt.world import make_world, free_fraction

here = pathlib.Path(__file__).resolve().parent
cfg = yaml.safe_load((here / "campaign.yaml").read_text())
cfg["policies"] = [(name, alpha) for name, alpha in cfg["policies"]]
cfg["environments"] = [(name, cov) for name, cov in cfg["environments"]]
cfg["straight_line"] = float(np.hypot(56.0, 56.0))

palette = {"rrtstar": "#444444", "neutral": "#1f77b4", "cvar0.1": "#2ca02c",
           "cvar0.5": "#ff7f0e", "cvar0.9": "#d62728"}

# ------------------------------------------------------------------
# the campaign

started = time.perf_counter()
rows, cells = run_campaign(cfg, processes=cfg["processes"],
                           csv_path=here / "results" / "campaign.csv")
write_summary(here / "results" / "summary.json", cfg, cells)
print("runs:", len(rows), "wall clock:", round(time.perf_counter() - started, 1), "s")

for name, coverage in cfg["environments"]:
    world = make_world(coverage, seed=0, half_width=cfg["half_width"])
    print(name, "coverage target", coverage, "obstacles", world.n_obstacles,
          "measured free fraction", round(free_fraction(world), 4))

# ------------------------------------------------------------------
# the results table

budget = round(cfg["budget_factor"] * cfg["straight_line"], 1)
print()
print("failure = execution over the traversal budget of", budget,
      "m, or no path found; worst case = 95th percentile of realised cost")
head = ["sigma", "policy", "success", "failure", "hazard", "mean len", "worst p95",
        "max", "clearance", "plan s"]
width = [6, 9, 8, 8, 7, 9, 10, 8, 10, 8]

def show(values):
    print(" ".join(str(v).rjust(w) for v, w in zip(values, width)))

for name, _ in cfg["environments"]:
    print()
    print(name, "environment")
    show(head)
    for sigma in cfg["noise_levels"]:
        for policy, _ in cfg["policies"]:
            c = next(c for c in cells if (c["env"], c["sigma"], c["policy"]) == (name, sigma, policy))
            show([sigma, policy, round(c["success_rate"], 3), round(c["failure_rate"], 4),
                  round(c["hazard_rate"], 3),
                  round(c["mean_path_length"], 2), round(c["worst_case_p95"], 1),
                  round(c["worst_case_max"], 1), round(c["mean_clearance"], 2),
                  round(c["mean_plan_time"], 3)])

# ------------------------------------------------------------------
# figure 1: example trees and paths in the three environments

show_policies = ["rrtstar", "neutral", "cvar0.9"]
labels = {"rrtstar": "RRT* (path length)", "neutral": "RA-RRT* risk-neutral (mean)",
          "cvar0.9": "RA-RRT* risk-averse (CVaR 0.9)"}
sigma_fig = cfg["noise_levels"][-1]

fig, axes = plt.subplots(1, 3, figsize=(12.6, 4.6), constrained_layout=True)
for ax, (name, coverage) in zip(axes, cfg["environments"]):
    world = make_world(coverage, seed=0, half_width=cfg["half_width"])
    for centre, radius in zip(world.centers, world.radii):
        ax.add_patch(plt.Circle(centre, radius, color="0.15", zorder=1))

    drawn_tree = False
    for policy in show_policies:
        alpha = dict(cfg["policies"])[policy]
        cost = CostModel(sigma=sigma_fig, alpha=alpha, n_samples=cfg["n_samples"],
                         kappa=cfg["kappa"], d_hazard=cfg["d_hazard"],
                         p_max=cfg["p_max"], seed=cfg["crn_seed"])
        result = plan(world, cost, iterations=cfg["iterations"], step=cfg["step"],
                      goal_bias=cfg["goal_bias"], seed=cfg["plan_seed"], keep_tree=True)
        if not drawn_tree:
            pts, parent = result["tree_points"], result["tree_parent"]
            child = np.nonzero(parent >= 0)[0]
            edges = np.stack([pts[child], pts[parent[child]]], axis=1)
            ax.add_collection(LineCollection(edges, colors="0.75", linewidths=0.3, zorder=2))
            drawn_tree = True
        if result["path"] is None:
            continue
        lengths, clearances = path_geometry(world, result["path"])
        ax.plot(result["path"][:, 0], result["path"][:, 1], color=palette[policy],
                linewidth=2.0, zorder=3,
                label=labels[policy] + "  len " + str(round(lengths.sum(), 1))
                      + ", clr " + str(round(clearances.min(), 2)))

    ax.plot(*world.start, "o", color="#00a000", markersize=8, zorder=4)
    ax.plot(*world.goal, "*", color="#d62728", markersize=14, zorder=4)
    ax.set_xlim(-cfg["half_width"], cfg["half_width"])
    ax.set_ylim(-cfg["half_width"], cfg["half_width"])
    ax.set_aspect("equal")
    ax.set_title(name + " environment")
    ax.set_xlabel("x [m]")
    ax.legend(loc="lower right", fontsize=7, framealpha=0.9)
axes[0].set_ylabel("y [m]")
fig.suptitle("RRT* tree and planned paths, noise level " + str(sigma_fig))
fig.savefig(here / "figures" / "paths_by_environment.svg")
fig.savefig(here / "figures" / "paths_by_environment.pdf")
plt.close(fig)

# ------------------------------------------------------------------
# figure 2: failure rate and worst-case length against the noise level

fig, axes = plt.subplots(2, 3, figsize=(12.0, 6.4), sharex=True, constrained_layout=True)
for column, (name, _) in enumerate(cfg["environments"]):
    for policy, _ in cfg["policies"]:
        picked = [next(c for c in cells if (c["env"], c["sigma"], c["policy"]) == (name, s, policy))
                  for s in cfg["noise_levels"]]
        axes[0, column].plot(cfg["noise_levels"], [c["failure_rate"] for c in picked],
                             "o-", color=palette[policy], label=policy)
        axes[1, column].plot(cfg["noise_levels"], [c["worst_case_p95"] for c in picked],
                             "o-", color=palette[policy], label=policy)
    axes[0, column].set_title(name + " environment")
    axes[1, column].set_xlabel("noise level sigma")
    axes[1, column].set_xscale("log")
axes[0, 0].set_ylabel("failure rate")
axes[1, 0].set_ylabel("worst-case path length [m], p95")
axes[0, 0].legend(fontsize=8)
fig.savefig(here / "figures" / "failure_and_worstcase.svg")
fig.savefig(here / "figures" / "failure_and_worstcase.pdf")
plt.close(fig)

# ------------------------------------------------------------------
# figure 3: what the risk level buys and what it costs

fig, axes = plt.subplots(1, 3, figsize=(12.0, 4.0), constrained_layout=True)
for ax, (name, _) in zip(axes, cfg["environments"]):
    for policy, _ in cfg["policies"]:
        c = next(c for c in cells
                 if (c["env"], c["sigma"], c["policy"]) == (name, sigma_fig, policy))
        ax.plot(c["mean_path_length"], c["worst_case_p95"], "o", color=palette[policy],
                markersize=9, label=policy)
    ax.set_title(name + " environment")
    ax.set_xlabel("mean planned path length [m]")
    ax.margins(0.18)
axes[0].set_ylabel("worst-case path length [m], p95")
axes[0].legend(fontsize=8)
fig.suptitle("premium against protection, noise level " + str(sigma_fig))
fig.savefig(here / "figures" / "premium_against_protection.svg")
fig.savefig(here / "figures" / "premium_against_protection.pdf")
plt.close(fig)

print()
print("figures:", sorted(p.name for p in (here / "figures").glob("*")))
