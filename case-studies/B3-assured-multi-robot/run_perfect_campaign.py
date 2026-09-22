# The coordination study as a PERFECT campaign: the coordination configuration
# (which robot gets which station pair, and the robustness margin the plan must
# hold) is the design, the tracking disturbance a fleet is executed under is the
# environment, and one trial synthesises the joint plan, executes it once, scores
# it and writes the verdicts back.
#
#   python run_perfect_campaign.py --submit --url http://127.0.0.1:5001
#   python run_perfect_campaign.py --collect --url http://127.0.0.1:5001
#
# --submit loads the coordinator library, creates one design per configuration,
# the environment template and one environment per disturbance level and seed,
# then one experiment per design and environment with a trial enqueued, and waits
# for them. --collect reads the trials back through the same API, writes the
# campaign table and the per-design and per-cell aggregates, and draws the figures
# from them.
#
# The PERFECT example behind it is perfect/examples/multirobot-milp, whose
# components.json is the library this script loads.

import argparse
import csv
import json
import pathlib
import sys

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

here = pathlib.Path(__file__).parent
example = here / ".." / ".." / "perfect" / "examples" / "multirobot-milp"
tradesx_path = here / ".." / ".." / "trades-x"
if str(tradesx_path) not in sys.path:
    sys.path.insert(0, str(tradesx_path))

from tradesx import ddo_api                    # noqa: E402

from assured_ma import specs                   # noqa: E402

results = here / "results" / "perfect"
figures = here / "figures"
fleet_file = here / "model" / "fleet_requirements.yaml"

TAG = "multirobot"

# The environments: three disturbance levels, three seeds each. The steady-state
# tracking error is sigma / sqrt(1 - 0.8^2), so 0.10, 0.15 and 0.20 m; 0.09 is the
# level the standalone run uses.
SIGMAS = [0.06, 0.09, 0.12]
SEEDS = [0, 1, 2]
MARGINS = [0.15, 0.35, 0.45, 0.5]
ROBOTS = ["AGR_1", "AGR_2", "AGR_3"]
COLORS = ["#1f77b4", "#d62728", "#2ca02c"]
SIGMA_COLOUR = {0.06: "#4c9f70", 0.09: "#e1a100", 0.12: "#b8322a"}


def library():
    return json.load(open(example / "components.json"))


def design_names():
    return [c["name"] for c in library()]


def parse_design(name):
    """alloc102-m0.35 -> ((1, 0, 2), 0.35)"""
    perm, margin = name[len("alloc"):].split("-m")
    return tuple(int(c) for c in perm), float(margin)


def campaign_designs():
    """One design per coordination configuration, over that configuration's implementation."""
    return {name: [name] for name in design_names()}


def environment_name(sigma, seed):
    return "sigma" + str(sigma) + "-seed" + str(seed)


def campaign_environments():
    return {environment_name(s, k): {"sigma": s, "seed": k} for s in SIGMAS for k in SEEDS}


# ------------------------------------------------------------------
# submit

def do_submit(server, wait_seconds):
    designs = campaign_designs()
    environments = campaign_environments()
    template = json.load(open(example / "environment_template.json"))[0]

    print("designs:", len(designs), "environments:", len(environments),
          "trials:", len(designs) * len(environments))
    ids = ddo_api.submit(server, library(), designs,
                         (template["name"], template["specification"]),
                         environments, TAG)
    print("experiments:", len(ids["experiments"]), "trials enqueued:", len(ids["trials"]))

    seen = [-1]

    def report(done, total):
        if done != seen[0]:
            seen[0] = done
            print("  ", done, "/", total, "shut down", flush=True)

    done, total = ddo_api.wait(server, TAG, timeout=wait_seconds, poll=10.0, report=report)
    print("finished:", done, "of", total)
    return done == total


# ------------------------------------------------------------------
# collect: the tables

def fmt(v):
    # numpy scalars repr themselves as np.float64(...), so everything numeric is
    # coerced to a plain Python number first. Rounding to nine places keeps two
    # collections of the same database byte-identical.
    if v is None or v == "":
        return ""
    if isinstance(v, (bool, np.bool_)):
        return str(int(v))
    if isinstance(v, (float, np.floating)):
        return repr(round(float(v), 9))
    if isinstance(v, (int, np.integer)):
        return str(int(v))
    return v


def per_robot(r, key):
    return [None] * len(ROBOTS) if r.get(key) is None else list(r[key])


CAMPAIGN_COLUMNS = (["design", "environment", "experiment_id", "trial_id", "state",
                     "wall_seconds", "allocation", "required_margin", "sigma", "seed",
                     "feasible", "stop", "mip_status", "nodes", "mip_gap", "dual_bound",
                     "solve_wall", "effort", "dense_margin"]
                    + ["planned_rho_" + r for r in ROBOTS]
                    + ["executed_rho_" + r for r in ROBOTS]
                    + ["min_rho", "violations"]
                    + ["binding_" + r for r in ROBOTS])


def flat(r):
    """One trial as one row of the campaign table."""
    row = {k: r.get(k) for k in CAMPAIGN_COLUMNS}
    row["allocation"] = "-".join(str(a) for a in r["allocation"])
    for key, prefix in (("planned_rho", "planned_rho_"), ("executed_rho", "executed_rho_"),
                        ("binding", "binding_")):
        for robot, v in zip(ROBOTS, per_robot(r, key)):
            row[prefix + robot] = v
    return row


def write_table(rows, columns, path):
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(columns)
        for r in rows:
            w.writerow([fmt(r.get(c)) for c in columns])


def by_design(rows):
    out = {}
    for r in rows:
        out.setdefault(r["design"], []).append(r)
    return out


def distinct_plans(trials):
    return len({json.dumps(t["plan"]) for t in trials})


def design_table(rows):
    """One row per design: the solve, which is the same in every trial of a design,
    and the executions, which differ by environment."""
    table = []
    for name, trials in sorted(by_design(rows).items()):
        allocation, margin = parse_design(name)
        ok = [t for t in trials if t["feasible"]]
        d = {"design": name, "allocation": "-".join(map(str, allocation)),
             "required_margin": margin, "trials": len(trials), "feasible_trials": len(ok),
             "stop": "/".join(sorted({t["stop"] for t in trials})),
             "solve_wall_mean": float(np.mean([t["solve_wall"] for t in trials])),
             "solve_wall_max": float(np.max([t["solve_wall"] for t in trials]))}
        if ok:
            rho = np.array([t["executed_rho"] for t in ok])
            d.update({
                "nodes": float(np.mean([t["nodes"] for t in ok])),
                "mip_gap": float(np.mean([t["mip_gap"] for t in ok])),
                "effort": float(np.mean([t["effort"] for t in ok])),
                "planned_min_rho": float(np.mean([t["planned_min_rho"] for t in ok])),
                "distinct_plans": distinct_plans(ok),
                "mean_min_rho": float(rho.min(axis=1).mean()),
                "worst_min_rho": float(rho.min()),
                "violating_trials": int((rho.min(axis=1) < 0).sum()),
            })
            for i, robot in enumerate(ROBOTS):
                d["violations_" + robot] = int((rho[:, i] < 0).sum())
        table.append(d)
    ranked = sorted([d for d in table if d["feasible_trials"]],
                    key=lambda d: (-d["worst_min_rho"], -d["mean_min_rho"], d["effort"],
                                   d["design"]))
    for k, d in enumerate(ranked):
        d["rank"] = k + 1
    return table


DESIGN_COLUMNS = (["design", "allocation", "required_margin", "trials", "feasible_trials",
                   "stop", "nodes", "mip_gap", "effort", "planned_min_rho", "distinct_plans",
                   "solve_wall_mean", "solve_wall_max", "mean_min_rho", "worst_min_rho",
                   "violating_trials"]
                  + ["violations_" + r for r in ROBOTS] + ["rank"])


def cell_table(rows):
    """One row per design and disturbance level, pooling the seeds."""
    cells = []
    for name, trials in sorted(by_design(rows).items()):
        allocation, margin = parse_design(name)
        for sigma in SIGMAS:
            ok = [t for t in trials if t["sigma"] == sigma and t["feasible"]]
            c = {"design": name, "allocation": "-".join(map(str, allocation)),
                 "required_margin": margin, "sigma": sigma,
                 "trials": sum(1 for t in trials if t["sigma"] == sigma)}
            if ok:
                m = np.array([t["min_rho"] for t in ok])
                c.update({"mean_min_rho": float(m.mean()), "worst_min_rho": float(m.min()),
                          "violating_trials": int((m < 0).sum())})
            cells.append(c)
    return cells


CELL_COLUMNS = ["design", "allocation", "required_margin", "sigma", "trials",
                "mean_min_rho", "worst_min_rho", "violating_trials"]


def margin_table(rows):
    """The designs of one margin pooled: what the margin buys, and what it costs."""
    out = []
    for margin in MARGINS:
        trials = [r for r in rows if r["required_margin"] == margin]
        ok = [t for t in trials if t["feasible"]]
        m = {"required_margin": margin,
             "designs": len({t["design"] for t in trials}),
             "feasible_designs": len({t["design"] for t in ok}),
             "trials": len(trials), "feasible_trials": len(ok),
             "solve_wall_mean": float(np.mean([t["solve_wall"] for t in trials]))}
        if ok:
            mins = np.array([t["min_rho"] for t in ok])
            m.update({"violating_trials": int((mins < 0).sum()),
                      "violation_rate": float((mins < 0).mean()),
                      "mean_min_rho": float(mins.mean()),
                      "mip_gap_mean": float(np.mean([t["mip_gap"] for t in ok])),
                      "effort_mean": float(np.mean([t["effort"] for t in ok]))})
        out.append(m)
    return out


def binding_kind(label):
    if label.startswith("sep("):
        return "separation"
    if label.startswith("OBS_"):
        return "obstacle"
    return "station"


def violated_conjuncts(rows):
    """Which kind of conjunct set the value of every robot that violated its formula."""
    counts = {"separation": 0, "obstacle": 0, "station": 0}
    for r in rows:
        if not r["feasible"]:
            continue
        for v, label in zip(r["executed_rho"], r["binding"]):
            if v < 0:
                counts[binding_kind(label)] += 1
    return counts


def trace(design_row, rows):
    """The plan and every executed trace of one design, for the trajectory panel."""
    trials = sorted([r for r in rows if r["design"] == design_row["design"] and r["feasible"]],
                    key=lambda r: (r["sigma"], r["seed"]))
    return {"design": design_row["design"], "worst_min_rho": design_row["worst_min_rho"],
            "effort": design_row["effort"], "plan": trials[0]["plan"],
            "executed": {environment_name(r["sigma"], r["seed"]): r["executed"] for r in trials},
            "min_rho": {environment_name(r["sigma"], r["seed"]): r["min_rho"] for r in trials}}


def rounded(v):
    if isinstance(v, dict):
        return {k: rounded(x) for k, x in v.items()}
    if isinstance(v, list):
        return [rounded(x) for x in v]
    if isinstance(v, (float, np.floating)):
        return round(float(v), 9)
    if isinstance(v, (np.integer,)):
        return int(v)
    return v


def summarise(rows, designs, margins):
    ranked = sorted([d for d in designs if "rank" in d], key=lambda d: d["rank"])
    return rounded({
        "tag": TAG,
        "grid": {"designs": design_names(), "sigmas": SIGMAS, "seeds": SEEDS,
                 "margins": MARGINS},
        "trials": len(rows),
        "states": sorted({r["state"] for r in rows}),
        "successful": sum("SUCCESSFUL" in (r["state"] or "") for r in rows),
        "feasible_trials": sum(bool(r["feasible"]) for r in rows),
        "stops": {s: sum(r["stop"] == s for r in rows) for s in sorted({r["stop"] for r in rows})},
        "most_distinct_plans_in_one_design": max(d.get("distinct_plans", 1) for d in designs),
        "margins": margins,
        "violated_conjuncts": violated_conjuncts(rows),
        "ranking": [d["design"] for d in ranked],
        "top": trace(ranked[0], rows),
        "bottom": trace(ranked[-1], rows),
    })


# ------------------------------------------------------------------
# collect: printing

def show(v, n=3):
    return "-" if v is None else str(round(v, n))


def print_designs(designs):
    print()
    print("design           stop        nodes  solve s  gap     effort  planned  "
          "mean min  worst min  violating  AGR_1 AGR_2 AGR_3  rank")
    for d in designs:
        print(d["design"].ljust(16), d["stop"].ljust(10),
              ("-" if d.get("nodes") is None else str(int(round(d["nodes"])))).rjust(6),
              show(d["solve_wall_mean"], 1).rjust(8),
              show(d.get("mip_gap")).rjust(6), show(d.get("effort"), 2).rjust(8),
              show(d.get("planned_min_rho")).rjust(8), show(d.get("mean_min_rho")).rjust(9),
              show(d.get("worst_min_rho")).rjust(10),
              (str(d.get("violating_trials", "-")) + "/" + str(d["trials"])).rjust(10),
              str(d.get("violations_AGR_1", "-")).rjust(6),
              str(d.get("violations_AGR_2", "-")).rjust(5),
              str(d.get("violations_AGR_3", "-")).rjust(5),
              str(d.get("rank", "-")).rjust(5))


def print_margins(margins):
    print()
    print("margin  designs  feasible  trials  violating  rate    mean min rho  "
          "solve s  gap     effort")
    for m in margins:
        print(str(m["required_margin"]).ljust(7), str(m["designs"]).rjust(7),
              str(m["feasible_designs"]).rjust(9), str(m["trials"]).rjust(7),
              str(m.get("violating_trials", "-")).rjust(10),
              show(m.get("violation_rate")).rjust(6), show(m.get("mean_min_rho")).rjust(13),
              show(m["solve_wall_mean"], 2).rjust(8), show(m.get("mip_gap_mean")).rjust(6),
              show(m.get("effort_mean"), 2).rjust(8))


def print_cells(cells):
    print()
    print("violating trials of 3 seeds, by design and disturbance level")
    print("design           " + "  ".join(("sigma " + str(s)).rjust(10) for s in SIGMAS))
    for name in design_names():
        picked = [c for c in cells if c["design"] == name]
        if not picked or "violating_trials" not in picked[0]:
            continue
        print(name.ljust(16), "  ".join(
            (str(c["violating_trials"]) + " (" + show(c["mean_min_rho"]) + ")").rjust(10)
            for c in picked))


# ------------------------------------------------------------------
# collect: the figures

def save(fig, stem):
    fig.savefig(figures / (stem + ".svg"))
    fig.savefig(figures / (stem + ".pdf"))
    plt.close(fig)


def draw_min_rho(rows):
    """Executed min rho of every trial, by design and disturbance level."""
    feasible = [m for m in MARGINS if any(r["feasible"] and r["required_margin"] == m
                                           for r in rows)]
    perms = sorted({tuple(r["allocation"]) for r in rows})
    fig, axes = plt.subplots(1, len(feasible), figsize=(4.2 * len(feasible), 4.0),
                             sharey=True, constrained_layout=True)
    for ax, margin in zip(np.atleast_1d(axes), feasible):
        for j, sigma in enumerate(SIGMAS):
            pick = [r for r in rows if r["required_margin"] == margin and r["sigma"] == sigma
                    and r["feasible"]]
            x = np.array([perms.index(tuple(r["allocation"])) for r in pick]) + (j - 1) * 0.22
            ax.plot(x, [r["min_rho"] for r in pick], "o", ms=4.5, alpha=0.85,
                    color=SIGMA_COLOUR[sigma], label="sigma " + str(sigma))
        ax.axhline(0.0, color="k", lw=0.9)
        ax.axhline(margin, color="0.5", lw=0.8, ls="--")
        ax.set_xticks(range(len(perms)))
        ax.set_xticklabels(["".join(map(str, p)) for p in perms])
        ax.set_xlabel("allocation")
        ax.set_title("required margin " + str(margin) + " m")
    np.atleast_1d(axes)[0].set_ylabel("executed min rho over the three robots [m]")
    np.atleast_1d(axes)[0].legend(fontsize=7, loc="lower left")
    infeasible = [m for m in MARGINS if m not in feasible]
    fig.suptitle("Executed robustness of every trial (dashed: the margin the plan holds)"
                 + ("" if not infeasible else "; margin " + ", ".join(map(str, infeasible))
                    + " m infeasible for every allocation"))
    save(fig, "perfect_min_rho")


def draw_solve(rows):
    """What each margin costs the solver and the robots."""
    fig, axes = plt.subplots(1, 3, figsize=(12.0, 3.8), constrained_layout=True)
    x = {m: k for k, m in enumerate(MARGINS)}
    offsets = np.linspace(-0.25, 0.25, 6)
    perms = sorted({tuple(r["allocation"]) for r in rows})
    for r in rows:
        dx = offsets[perms.index(tuple(r["allocation"]))]
        axes[0].plot(x[r["required_margin"]] + dx, r["solve_wall"], ".", ms=4,
                     color="0.25" if r["feasible"] else "#b8322a")
    firsts = {}
    for r in rows:
        firsts.setdefault(r["design"], r)
    for r in firsts.values():
        if not r["feasible"]:
            continue
        dx = offsets[perms.index(tuple(r["allocation"]))]
        axes[1].plot(x[r["required_margin"]] + dx, r["mip_gap"], "o", ms=5, color="0.25")
        axes[2].plot(x[r["required_margin"]] + dx, r["effort"], "o", ms=5, color="0.25")
    axes[0].set_yscale("log")
    axes[0].set_ylabel("solve wall [s], every trial")
    axes[1].set_ylabel("relative MIP gap at the stop")
    axes[2].set_ylabel("control effort, 1-norm of the accelerations")
    for ax in axes:
        ax.set_xticks(range(len(MARGINS)))
        ax.set_xticklabels([str(m) for m in MARGINS])
        ax.set_xlim(-0.5, len(MARGINS) - 0.5)
        ax.set_xlabel("required margin [m]")
    for m in MARGINS:
        if not any(r["feasible"] and r["required_margin"] == m for r in rows):
            for ax in axes[1:]:
                ax.text(x[m], 0.5, "no plan:\ninfeasible", transform=ax.get_xaxis_transform(),
                        ha="center", va="center", fontsize=8, color="#b8322a")
    fig.suptitle("The solve, by required margin (one point per allocation; red: proven infeasible)")
    save(fig, "perfect_solve")


def draw_violations(rows):
    feasible = [m for m in MARGINS if any(r["feasible"] and r["required_margin"] == m
                                           for r in rows)]
    fig, axes = plt.subplots(1, len(SIGMAS), figsize=(12.0, 3.8), sharey=True,
                             constrained_layout=True)
    for ax, sigma in zip(axes, SIGMAS):
        for i, robot in enumerate(ROBOTS):
            counts = [sum(1 for r in rows if r["feasible"] and r["sigma"] == sigma
                          and r["required_margin"] == m and r["executed_rho"][i] < 0)
                      for m in feasible]
            ax.bar(np.arange(len(feasible)) + (i - 1) * 0.26, counts, 0.24, color=COLORS[i],
                   label=robot)
        n = sum(1 for r in rows if r["feasible"] and r["sigma"] == sigma
                and r["required_margin"] == feasible[0])
        ax.set_xticks(range(len(feasible)))
        ax.set_xticklabels([str(m) for m in feasible])
        ax.set_xlabel("required margin [m]")
        ax.set_title("sigma " + str(sigma) + " (" + str(n) + " trials per margin)")
    axes[0].set_ylabel("trials in which the robot's executed rho < 0")
    axes[0].legend(fontsize=8)
    save(fig, "perfect_violations")


def draw_trajectories(summary):
    """The top- and the bottom-ranked design: the plan every trial of the design
    returned, and the executed traces of all its trials."""
    fig, axes = plt.subplots(1, 2, figsize=(13.0, 5.2), constrained_layout=True)
    for ax, key in zip(axes, ("top", "bottom")):
        t = summary[key]
        allocation, margin = parse_design(t["design"])
        fleet = specs.load_fleet(fleet_file, allocation=allocation)
        cfg = fleet["cfg"]
        for o in fleet["obstacles"]:
            v = o.vertices()
            ax.fill(v[:, 0], v[:, 1], color="0.65", edgecolor="0.3", zorder=1)
        for i, goals in enumerate(fleet["goal_sets"]):
            for g, w in goals:
                v = g.vertices()
                ax.fill(v[:, 0], v[:, 1], color=COLORS[i], alpha=0.12, zorder=1)
                ax.plot(np.append(v[:, 0], v[0, 0]), np.append(v[:, 1], v[0, 1]), ls="--",
                        lw=1.0, color=COLORS[i], zorder=2)
                ax.text(v[:, 0].mean(), v[:, 1].max() + 0.12,
                        g.name + " k in [" + str(w[0]) + "," + str(w[1]) + "]",
                        ha="center", fontsize=6.5, color=COLORS[i], zorder=3)
        plan = np.array(t["plan"])
        for env in sorted(t["executed"]):
            ex = np.array(t["executed"][env])
            for i in range(ex.shape[0]):
                ax.plot(ex[i, :, 0], ex[i, :, 1], lw=0.8, alpha=0.55, color=COLORS[i], zorder=4)
        for i in range(plan.shape[0]):
            ax.plot(plan[i, :, 0], plan[i, :, 1], ls="--", lw=1.8, color="k", zorder=5)
            ax.plot(plan[i, :, 0], plan[i, :, 1], ls="--", lw=1.2, color=COLORS[i], zorder=6,
                    label=ROBOTS[i])
            ax.plot(plan[i, 0, 0], plan[i, 0, 1], "s", ms=7, color=COLORS[i], mec="k",
                    mew=0.6, zorder=7)
        ax.set_xlim(cfg["workspace"]["x"])
        ax.set_ylim(cfg["workspace"]["y"][0], cfg["workspace"]["y"][1] + 0.45)
        ax.set_aspect("equal")
        ax.set_xlabel("x [m]")
        ax.set_title(key + "-ranked design " + t["design"] + ": worst executed min rho "
                     + show(t["worst_min_rho"]) + " m, effort " + show(t["effort"], 2),
                     fontsize=9)
        ax.legend(loc="lower left", fontsize=7)
    axes[0].set_ylabel("y [m]")
    fig.suptitle("The plan each design's trials returned (dashed) and the executed traces "
                 "of all " + str(len(summary["top"]["executed"])) + " of its trials (solid)")
    save(fig, "perfect_trajectories")


# ------------------------------------------------------------------

def do_collect(server):
    results.mkdir(parents=True, exist_ok=True)
    figures.mkdir(parents=True, exist_ok=True)

    rows = ddo_api.collect(server, TAG)
    states = sorted({r["state"] for r in rows})
    print("trials collected:", len(rows), "states:", states)
    print("SUCCESSFUL trials:", sum("SUCCESSFUL" in (r["state"] or "") for r in rows))
    print("feasible:", sum(bool(r["feasible"]) for r in rows), "of", len(rows))
    print("stopped by:", {s: sum(r["stop"] == s for r in rows)
                          for s in sorted({r["stop"] for r in rows})})

    designs = design_table(rows)
    cells = cell_table(rows)
    margins = margin_table(rows)
    summary = summarise(rows, designs, margins)
    write_table([flat(r) for r in rows], CAMPAIGN_COLUMNS, results / "campaign.csv")
    write_table(designs, DESIGN_COLUMNS, results / "designs.csv")
    write_table(cells, CELL_COLUMNS, results / "cells.csv")
    with open(results / "summary.json", "w") as f:
        json.dump(summary, f, indent=1)
        f.write("\n")

    print("most distinct plans returned by the trials of one design:",
          summary["most_distinct_plans_in_one_design"])
    print_designs(designs)
    print_margins(margins)
    print_cells(cells)
    print()
    print("the conjunct that set the value of each violated formula:",
          summary["violated_conjuncts"])
    print("top-ranked:", summary["ranking"][:3], "bottom-ranked:", summary["ranking"][-1])

    draw_min_rho(rows)
    draw_solve(rows)
    draw_violations(rows)
    draw_trajectories(summary)
    print()
    print("results written to", shown(results))
    print("figures written to", shown(figures))
    return rows, designs, summary


def shown(path):
    """A path inside this directory relative to it, any other path as it is."""
    path = pathlib.Path(path).resolve()
    return path.relative_to(here.resolve()) if path.is_relative_to(here.resolve()) else path


def main(argv=None):
    global results, figures
    p = argparse.ArgumentParser(description="the assured multi-robot coordination campaign on PERFECT")
    p.add_argument("--url", default=ddo_api.DEFAULT_URL, help="the PERFECT server")
    p.add_argument("--submit", action="store_true", help="create and run the campaign")
    p.add_argument("--collect", action="store_true", help="read it back, tabulate and draw")
    p.add_argument("--wait", type=float, default=4800.0, help="seconds to wait for the trials")
    p.add_argument("--out", help="write the tables and the figures to this directory "
                   "instead of results/perfect and figures/")
    args = p.parse_args(argv)
    if not (args.submit or args.collect):
        p.error("give --submit, --collect, or both")
    if args.out:
        results = figures = pathlib.Path(args.out)

    server = ddo_api.Server(args.url)
    if args.submit:
        do_submit(server, args.wait)
    if args.collect:
        do_collect(server)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
