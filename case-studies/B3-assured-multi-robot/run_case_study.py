"""Case study B3 end to end, seeded and reproducible.

    fleet requirement -> per-robot missions -> satisfy allocation -> STL specs
    -> MILP synthesis -> execution under tracking noise -> VERITAS robustness
    -> write-back into the AGR model -> nav_msgs/msg/Path export

Everything the run produces goes to results/ and figures/. See README.md.
"""

import argparse
import itertools
import math
import time
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from assured_ma import encode, execute, ros_export, synth, writeback
from assured_ma import robustness as rb
from assured_ma import specs

HERE = Path(__file__).parent
COLORS = ["#1f77b4", "#d62728", "#2ca02c"]


def make_problem(cfg, starts, required):
    ws = cfg["workspace"]
    return encode.Problem(N=cfg["horizon"]["steps"], dt=cfg["horizon"]["dt"],
                          v_max=cfg["dynamics"]["v_max"], a_max=cfg["dynamics"]["a_max"],
                          ws_lo=np.array([ws["x"][0], ws["y"][0]], float),
                          ws_hi=np.array([ws["x"][1], ws["y"][1]], float),
                          starts=starts, rho_cap=cfg["synthesis"]["rho_cap"],
                          effort_weight=cfg["synthesis"]["effort_weight"],
                          rho_required=required)


def decoupled(fleet):
    """Each robot's own formula with the team-separation conjunct dropped, re-indexed
    to a single-robot problem. Used by --per-robot-optima."""
    out = []
    for i, goals in enumerate(fleet["goal_sets"]):
        reach = [specs.Ev(w[0], w[1], specs.InSet(0, g, g.name)) for g, w in goals]
        avoid = [specs.OutSet(0, o, o.name) for o in fleet["obstacles"]]
        out.append(specs.And(tuple(reach) + (specs.Alw(0, fleet["N"], specs.And(tuple(avoid))),),
                             "phi_{}".format(i + 1)))
    return out


def score(fleet, traj):
    """VERITAS's data-driven check: one robustness value per robot, per trajectory."""
    return np.array([rb.rho(s, traj) for s in fleet["specs"]])


# ------------------------------------------------------------------
# figures

def plot_environment(fleet, plan, executed, path):
    cfg = fleet["cfg"]
    fig, ax = plt.subplots(figsize=(8.0, 6.2))
    for o in fleet["obstacles"]:
        v = o.vertices()
        ax.fill(v[:, 0], v[:, 1], color="0.65", edgecolor="0.3", zorder=1)
        ax.text(v[:, 0].mean(), v[:, 1].mean(), o.name.replace("OBS_", ""), ha="center",
                va="center", fontsize=6.5, color="0.15", zorder=3)
    for i, goals in enumerate(fleet["goal_sets"]):
        for g, w in goals:
            v = g.vertices()
            ax.fill(v[:, 0], v[:, 1], color=COLORS[i], alpha=0.12, zorder=1)
            ax.plot(np.append(v[:, 0], v[0, 0]), np.append(v[:, 1], v[0, 1]), ls="--",
                    lw=1.0, color=COLORS[i], zorder=2)
            ax.text(v[:, 0].mean(), v[:, 1].max() + 0.12,
                    "{} k in [{},{}]".format(g.name, w[0], w[1]), ha="center",
                    fontsize=6.5, color=COLORS[i], zorder=3)
    for i in range(plan.shape[0]):
        ax.plot(plan[i, :, 0], plan[i, :, 1], ls="--", lw=1.2, color=COLORS[i], alpha=0.65,
                label="AGR_{} plan".format(i + 1), zorder=4)
        ax.plot(executed[i, :, 0], executed[i, :, 1], lw=1.9, color=COLORS[i],
                label="AGR_{} executed".format(i + 1), zorder=5)
        ax.plot(executed[i, :, 0], executed[i, :, 1], ".", ms=3.5, color=COLORS[i], zorder=6)
        ax.plot(plan[i, 0, 0], plan[i, 0, 1], "s", ms=7, color=COLORS[i], mec="k", mew=0.6,
                zorder=7)
    ax.set_xlim(cfg["workspace"]["x"])
    ax.set_ylim(cfg["workspace"]["y"][0], cfg["workspace"]["y"][1] + 0.45)
    ax.set_aspect("equal")
    ax.set_xlabel("x [m]")
    ax.set_ylabel("y [m]")
    ax.set_title("MILP plans (dashed) and executed trajectories (solid), seed {}"
                 .format(cfg["execution"]["seed"]))
    ax.legend(loc="lower left", fontsize=7, ncol=3, framealpha=0.9)
    save(fig, path)


def plot_robustness(planned, executed, path):
    fig, ax = plt.subplots(figsize=(5.4, 3.4))
    x = np.arange(len(planned))
    ax.bar(x - 0.19, planned, 0.36, color="0.72", edgecolor="0.3", label="planned")
    ax.bar(x + 0.19, executed, 0.36, color=[COLORS[i] for i in x], label="executed")
    for xi, v in zip(x - 0.19, planned):
        ax.text(xi, v + 0.012 * np.sign(v or 1), round(float(v), 3), ha="center",
                va="bottom" if v >= 0 else "top", fontsize=7)
    for xi, v in zip(x + 0.19, executed):
        ax.text(xi, v + 0.012 * np.sign(v or 1), round(float(v), 3), ha="center",
                va="bottom" if v >= 0 else "top", fontsize=7)
    ax.axhline(0.0, color="k", lw=0.9)
    ax.set_xticks(x)
    ax.set_xticklabels(["AGR_{}\nphi_{}".format(i + 1, i + 1) for i in x])
    ax.set_ylabel("STL robustness rho [m]")
    ax.set_title("VERITAS goal-satisfaction values")
    ax.legend(fontsize=7)
    save(fig, path)


def plot_sweep(sweep, path):
    fig, ax = plt.subplots(figsize=(5.4, 3.4))
    for i in range(sweep.shape[1]):
        ax.plot(np.full(sweep.shape[0], i) + np.linspace(-0.16, 0.16, sweep.shape[0]),
                sweep[:, i], ".", ms=5, color=COLORS[i])
        ax.plot([i - 0.28, i + 0.28], [sweep[:, i].mean()] * 2, "-", lw=2, color="0.2")
    ax.axhline(0.0, color="k", lw=0.9)
    ax.set_xticks(range(sweep.shape[1]))
    ax.set_xticklabels(["AGR_{}".format(i + 1) for i in range(sweep.shape[1])])
    ax.set_ylabel("executed rho [m]")
    ax.set_title("Executed robustness over {} seeds (bar: mean)".format(sweep.shape[0]))
    save(fig, path)


def save(fig, stem):
    fig.tight_layout()
    fig.savefig(str(stem) + ".svg")
    fig.savefig(str(stem) + ".pdf")
    plt.close(fig)


# ------------------------------------------------------------------
# TRADES-X hook: task allocation as a design variable

def allocation_sweep(fleet, cfg, required, time_limit, gap):
    """Model-based stage: one MILP per allocation. Data-driven stage: score every
    allocation's executions over the seed sweep and rank by worst-case robustness."""
    ex = cfg["execution"]
    rows = []
    for perm in itertools.permutations(range(len(fleet["specs"]))):
        alt = specs.load_fleet(HERE / "model" / "fleet_requirements.yaml", allocation=perm)
        prob = make_problem(cfg, alt["starts"], required)
        out = synth.synthesise(prob, alt["specs"], mip_rel_gap=gap, time_limit=time_limit)
        row = {"allocation": list(perm), "status": out["status"], "wall_s": round(out["wall_s"], 1)}
        if "plan" in out:
            runs = execute.execute(out["plan"], ex["pole"], ex["sigma"], ex["clip_sigma"],
                                   ex["seed"], draws=ex["sweep_seeds"])
            sweep = np.stack([rb.rho(s, runs) for s in alt["specs"]], axis=1)
            row["effort"] = round(float(np.abs(out["acc"]).sum()), 3)
            row["planned_rho"] = [round(float(v), 4) for v in score(alt, out["plan"])]
            row["worst_executed_rho"] = round(float(sweep.min()), 4)
            row["mean_executed_rho"] = round(float(sweep.mean()), 4)
            row["violations"] = int((sweep < 0).sum())
        rows.append(row)
        print("  allocation {}  status {}  {} s  effort {}  worst executed rho {}".format(
            row["allocation"], row["status"], row["wall_s"],
            row.get("effort"), row.get("worst_executed_rho")), flush=True)
    return rows


# ------------------------------------------------------------------
# main

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--margin", type=float, default=None,
                    help="required STL robustness margin in metres; "
                         "default is synthesis.required_margin in the model file")
    ap.add_argument("--time-limit", type=float, default=None)
    ap.add_argument("--mip-gap", type=float, default=None)
    ap.add_argument("--allocation-sweep", action="store_true")
    ap.add_argument("--per-robot-optima", action="store_true",
                    help="how much robustness the map affords each robot on its own")
    ap.add_argument("--sweep-time-limit", type=float, default=60.0)
    ap.add_argument("--sweep-mip-gap", type=float, default=0.05)
    args = ap.parse_args()

    fleet = specs.load_fleet(HERE / "model" / "fleet_requirements.yaml")
    cfg = fleet["cfg"]
    margin = args.margin if args.margin is not None else cfg["synthesis"]["required_margin"]
    tl = args.time_limit if args.time_limit is not None else cfg["synthesis"]["time_limit_s"]
    gap = args.mip_gap if args.mip_gap is not None else cfg["synthesis"]["mip_rel_gap"]

    print("phi_i, one per robot:")
    for s in fleet["specs"]:
        print("  {} = {}".format(s.label, specs.pretty(s)))

    if args.per_robot_optima:
        print("\nlargest robustness each robot could hold alone (no team separation):")
        for i, s in enumerate(decoupled(fleet)):
            one = synth.synthesise(make_problem(cfg, fleet["starts"][i:i + 1], None), [s],
                                   mip_rel_gap=0.0, time_limit=tl)
            print("  AGR_{}  rho {}  ({}, {} s)".format(
                i + 1, round(float(one["z_root"][0]), 4), one["message"],
                round(one["wall_s"], 1)))

    prob = make_problem(cfg, fleet["starts"], margin)
    out = synth.synthesise(prob, fleet["specs"], mip_rel_gap=gap, time_limit=tl)
    print("\nMILP: {} variables ({} binary), {} constraints, {} nonzeros"
          .format(out["n_var"], out["n_bin"], out["n_con"], out["nnz"]))
    print("HiGHS: status {} ({}), {} s, relative gap {}"
          .format(out["status"], out["message"], round(out["wall_s"], 1),
                  round(out["mip_gap"], 5) if out["mip_gap"] is not None else None))
    if "plan" not in out:
        raise SystemExit("no plan returned")
    plan = out["plan"]

    ex = cfg["execution"]
    runs = execute.execute(plan, ex["pole"], ex["sigma"], ex["clip_sigma"], ex["seed"],
                           draws=ex["sweep_seeds"])
    executed = runs[0]
    planned_rho = score(fleet, plan)
    executed_rho = score(fleet, executed)
    sweep = np.stack([rb.rho(s, runs) for s in fleet["specs"]], axis=1)
    binding = [rb.explain(s, executed)[1] for s in fleet["specs"]]

    dense_margin = rb.dense_obstacle_margin(plan, fleet["obstacles"])
    print("smallest obstacle clearance along the interpolated plan: {} m"
          .format(round(dense_margin, 4)))

    print("\nrobot  spec   planned rho  executed rho  verdict    binding conjunct")
    for i, s in enumerate(fleet["specs"]):
        print("AGR_{}  {}  {:>11}  {:>12}  {:<9}  {}".format(
            i + 1, s.label, round(float(planned_rho[i]), 4), round(float(executed_rho[i]), 4),
            "satisfied" if executed_rho[i] > 0 else "violated", binding[i]))

    viol = (sweep < 0).sum(axis=0)
    print("\nover {} seeds of the same noise model, runs with rho < 0: {}"
          .format(sweep.shape[0], ", ".join("AGR_{} {}/{}".format(i + 1, int(v), sweep.shape[0])
                                            for i, v in enumerate(viol))))
    bad = np.argwhere(sweep < 0)
    if len(bad):
        d, r = bad[0]
        run = runs[d]
        print("first of them: draw {}, AGR_{}, rho {}, binding conjunct {}"
              .format(int(d), int(r) + 1, round(float(sweep[d, r]), 4),
                      rb.explain(fleet["specs"][int(r)], run)[1]))
    else:
        print("no draw in the sweep violated its specification")

    blocks = ["AGR_{}".format(i + 1) for i in range(len(fleet["specs"]))]
    verdicts = {b: {"rho": float(executed_rho[i]),
                    "verdict": "satisfied" if executed_rho[i] > 0 else "violated",
                    "binding": binding[i]} for i, b in enumerate(blocks)}
    writeback.write_model(HERE / "model" / "agr_fleet.yaml", verdicts)
    print("wrote goal_satisfaction into model/agr_fleet.yaml")

    res = HERE / "results"
    writeback.write_json(res / "goal_satisfaction.json",
                         {"source": "IDDMBSE case study B3, built for this release",
                          "seed": ex["seed"],
                          "blocks": {b: {"spec": fleet["specs"][i].label,
                                         "planned_rho": round(float(planned_rho[i]), 6),
                                         "goal_satisfaction": round(float(executed_rho[i]), 6),
                                         "verdict": verdicts[b]["verdict"],
                                         "binding_conjunct": binding[i]}
                                     for i, b in enumerate(blocks)}})
    writeback.write_json(res / "summary.json",
                         {"milp": {k: out[k] for k in
                                   ("status", "message", "wall_s", "n_var", "n_bin", "n_con",
                                    "nnz", "mip_gap")},
                          "required_margin": margin,
                          "control_effort_1norm": float(np.abs(out["acc"]).sum()),
                          "dense_path_obstacle_margin": dense_margin,
                          "planned_rho": [round(float(v), 6) for v in planned_rho],
                          "executed_rho": [round(float(v), 6) for v in executed_rho],
                          "seed_sweep": {"seeds": int(sweep.shape[0]),
                                         "violations_per_robot": [int(v) for v in viol],
                                         "rho": np.round(sweep, 6).tolist()},
                          "plan": np.round(plan, 6).tolist(),
                          "executed": np.round(executed, 6).tolist()})
    for i in range(plan.shape[0]):
        ros_export.write_path(res / "robot_{}_path.yaml".format(i + 1), plan[i],
                              cfg["horizon"]["dt"],
                              comment="MILP plan for AGR_{} ({}), IDDMBSE case study B3.\n"
                                      "Publish to the robot's Nav2 FollowPath action."
                                      .format(i + 1, fleet["specs"][i].label))
    print("wrote results/goal_satisfaction.json, results/summary.json and three "
          "results/robot_*_path.yaml")

    fig = HERE / "figures"
    plot_environment(fleet, plan, executed, fig / "trajectories")
    plot_robustness(planned_rho, executed_rho, fig / "robustness")
    plot_sweep(sweep, fig / "seed_sweep")
    print("wrote figures/trajectories, figures/robustness, figures/seed_sweep (svg and pdf)")

    if args.allocation_sweep:
        print("\nTRADES-X: task allocation sweep over all {} assignments"
              .format(math.factorial(len(fleet["specs"]))))
        t0 = time.perf_counter()
        rows = allocation_sweep(fleet, cfg, margin, args.sweep_time_limit,
                                args.sweep_mip_gap)
        ok = [r for r in rows if "worst_executed_rho" in r]
        best = max(ok, key=lambda r: r["worst_executed_rho"]) if ok else None
        writeback.write_json(res / "allocation_sweep.json",
                             {"time_limit_s": args.sweep_time_limit,
                              "mip_rel_gap": args.sweep_mip_gap,
                              "wall_s": round(time.perf_counter() - t0, 1),
                              "rows": rows, "best_by_worst_case_rho": best})
        if best is not None:
            print("best worst-case executed rho: allocation {} at {}"
                  .format(best["allocation"], best["worst_executed_rho"]))
        print("wrote results/allocation_sweep.json")


main()
