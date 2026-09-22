# The data-driven stage of the sensor-suite study, run against a live PERFECT
# server: ten designs over eighteen scenarios, one trial each, collected from
# PERFECT's trial table and ranked by the MAVF beside the model-based ranking.
#
#   python run_ddo_campaign.py --submit --url http://127.0.0.1:5001
#   python run_ddo_campaign.py --collect --url http://127.0.0.1:5001
#
# --submit loads the sensor library, creates the designs, the scenario template
# and the scenarios, then creates one experiment per design and scenario with a
# trial enqueued, and waits for them. --collect reads the trials back, writes
# the three result tables and the three figures, and prints the ranking.
#
# The PERFECT example behind it is perfect/examples/sensor-suite-sim, whose
# components.json is the sensor library this script loads.

import argparse
import csv
import itertools
import json
import pathlib

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from tradesx import ddo, ddo_api
from tradesx import requirements as reqs
from tradesx import sensitivity as sens
from tradesx.mavf import rank as mavf_rank
from tradesx.pareto import non_dominated

here = pathlib.Path(__file__).parent
data = here / "data"
results = here / "results"
figures = here / "figures"
example = here / ".." / ".." / ".." / "perfect" / "examples" / "sensor-suite-sim"

TAG = "ddo"

# The seven designs perfect/examples/SEILR1/robustness.bash carries, as decimal
# bitmasks over the thirteen sensor slots.
RECORDED = [4234, 785, 549, 2185, 4370, 4, 512]

# The scenario grid: rock density, ambient light, and the seed that picks the
# rock field.
CLUTTER = [0.2, 0.5, 0.8]
VISIBILITY = [1.0, 0.4]
SEEDS = [1, 2, 3]
N_DRAWS = 12

MBO_METRICS = ["cost", "power", "ram"]
MBO_SENSE = [-1, -1, -1]
DDO_METRICS = ["success_rate", "collision_rate", "time_to_goal", "tortuosity",
               "detection_distance", "battery_soc"]
DDO_SENSE = [1, -1, -1, -1, 1, 1]


# ------------------------------------------------------------------
# the design space

def subsets():
    """Every non-empty sensor subset, in the order the enumeration CSVs use."""
    return [s for k in range(1, 14) for s in itertools.combinations(range(13), k)]


def campaign_designs():
    """The ten designs the campaign runs, as {name: [sensor name, ...]}.

    Seven are the designs the study already carries. Three more are the best of
    the full model-based frontier under an equal-weight MAVF over the four
    model-based metrics, skipping any that are already in the seven: the point
    of the data-driven stage is to see whether the model-based ranking survives
    contact with a simulation.
    """
    all_subsets = subsets()
    row_of = {s: i + 1 for i, s in enumerate(all_subsets)}
    names = {}
    taken = set()
    for design_id in RECORDED:
        slots = tuple(sorted(c - 1 for c in ddo.design_components(design_id)))
        taken.add(row_of[slots])
        names["design-" + str(design_id)] = [sens.NAMES[i] for i in slots]

    metrics = np.loadtxt(data / "full_enumeration_4met.csv", delimiter=",")
    front = np.loadtxt(data / "pareto_full.csv", delimiter=",").astype(int)
    order, _ = mavf_rank(metrics[front - 1], [0.25] * 4, [-1, -1, -1, -1])
    picked = 0
    for k in order:
        row = int(front[k])
        if row in taken:
            continue
        names["frontier-" + str(row)] = [sens.NAMES[i] for i in all_subsets[row - 1]]
        picked += 1
        if picked == 3:
            break
    return names


def campaign_environments():
    grid = {}
    for clutter in CLUTTER:
        for visibility in VISIBILITY:
            for seed in SEEDS:
                name = "c" + str(clutter) + "-v" + str(visibility) + "-s" + str(seed)
                grid[name] = {"clutter": clutter, "visibility": visibility,
                              "seed": seed, "n_draws": N_DRAWS}
    return grid


def selection_matrix(designs):
    """(n_designs, 13) 0/1 matrix in the order `designs` lists them."""
    slot = {name: i for i, name in enumerate(sens.NAMES)}
    x = np.zeros((len(designs), 13))
    rows = np.concatenate([np.full(len(v), i) for i, v in enumerate(designs.values())])
    cols = np.concatenate([[slot[n] for n in v] for v in designs.values()])
    x[rows.astype(int), np.asarray(cols, dtype=int)] = 1.0
    return x


# ------------------------------------------------------------------
# submit

def do_submit(server, wait_seconds):
    designs = campaign_designs()
    environments = campaign_environments()
    components = json.load(open(example / "components.json"))
    template = json.load(open(example / "environment_template.json"))[0]

    print("designs:", len(designs), "scenarios:", len(environments),
          "trials:", len(designs) * len(environments))
    ids = ddo_api.submit(server, components, designs,
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

def write_campaign(rows, path):
    columns = (["design", "environment", "experiment_id", "trial_id", "state",
                "wall_seconds", "clutter", "visibility", "seed", "n_draws", "n_rocks"]
               + DDO_METRICS + ["path_length", "detection_rate", "stall_rate", "replans"]
               + MBO_METRICS)
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(columns)
        for r in rows:
            w.writerow([fmt(r.get(c)) for c in columns])


def write_metrics(designs, environments, table, path):
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["design", "environment"] + DDO_METRICS)
        for i, d in enumerate(designs):
            for j, e in enumerate(environments):
                w.writerow([d, e] + [fmt(v) for v in table[i, j]])


def write_ranking(designs, mbo, ddo_mean, scores, mbo_scores, path):
    order = np.argsort(-scores, kind="stable")
    mbo_order = np.argsort(-mbo_scores, kind="stable")
    place = np.empty(len(designs), dtype=int)
    place[order] = np.arange(1, len(designs) + 1)
    mbo_place = np.empty(len(designs), dtype=int)
    mbo_place[mbo_order] = np.arange(1, len(designs) + 1)
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["design", "mavf_rank", "mavf_score", "mbo_only_rank", "mbo_only_score"]
                   + MBO_METRICS + DDO_METRICS)
        for k in order:
            w.writerow([designs[k], place[k], fmt(scores[k]), mbo_place[k], fmt(mbo_scores[k])]
                       + [fmt(v) for v in mbo[k]] + [fmt(v) for v in ddo_mean[k]])
    return order, place, mbo_place


def fmt(v):
    # numpy scalars repr themselves as np.float64(...), so everything numeric is
    # coerced to a plain Python number first. Rounding to six places keeps two
    # collections of the same database byte-identical.
    if v is None:
        return ""
    if isinstance(v, (float, np.floating)):
        return repr(round(float(v), 6))
    if isinstance(v, (int, np.integer)):
        return str(int(v))
    return v


def do_collect(server):
    results.mkdir(exist_ok=True)
    figures.mkdir(exist_ok=True)

    designs = campaign_designs()
    environments = campaign_environments()
    names = sorted(designs)
    scenarios = sorted(environments)

    rows = ddo_api.collect(server, TAG)
    states = sorted({r["state"] for r in rows})
    print("trials collected:", len(rows), "states:", states)
    successful = [r for r in rows if "SUCCESSFUL" in (r["state"] or "")]
    print("SUCCESSFUL trials:", len(successful))

    write_campaign(rows, results / "ddo_campaign.csv")
    table = ddo_api.metric_table(rows, names, scenarios, DDO_METRICS)
    write_metrics(names, scenarios, table, results / "ddo_metrics.csv")
    ddo_mean = ddo_api.aggregate(table)

    # The model-based attributes are the catalogue's, known before anything ran.
    x = selection_matrix({n: designs[n] for n in names})
    mbo = np.column_stack([sens.cost(x), sens.power(x), sens.ram(x)])
    reported = ddo_api.metric_table(rows, names, scenarios, MBO_METRICS)
    gap = float(np.nanmax(np.abs(np.nanmean(reported, axis=1) - mbo)))
    print("max gap between the catalogue and what the trials reported:", gap)

    order, scores, mbo_order, mbo_scores = ddo_api.rank_designs(
        mbo, ddo_mean, MBO_SENSE, DDO_SENSE, reqs=reqs.load(here / "requirements.yaml"))
    order, place, mbo_place = write_ranking(
        names, mbo, ddo_mean, scores, mbo_scores, results / "mavf_ddo_ranking.csv")

    print()
    print("rank design            mavf   mbo-only  success  time[s]  tort   det[m]  cost[$]")
    for k in order:
        print(str(place[k]).rjust(4), names[k].ljust(17),
              round(float(scores[k]), 4), str(mbo_place[k]).rjust(7),
              str(round(float(ddo_mean[k, 0]), 3)).rjust(8),
              str(round(float(ddo_mean[k, 2]), 1)).rjust(8),
              str(round(float(ddo_mean[k, 3]), 3)).rjust(6),
              str(round(float(ddo_mean[k, 4]), 2)).rjust(7),
              str(int(mbo[k, 0])).rjust(8))

    draw_heatmap(names, scenarios, table)
    draw_ranking(names, scores, mbo_scores, order)
    draw_pareto(designs, names, order)
    print()
    print("results written to", results)
    print("figures written to", figures)
    return len(successful)


# ------------------------------------------------------------------
# figures

def save(fig, stem):
    fig.tight_layout()
    fig.savefig(figures / (stem + ".svg"))
    fig.savefig(figures / (stem + ".pdf"))
    plt.close(fig)


def draw_heatmap(names, scenarios, table):
    fig, ax = plt.subplots(figsize=(8.5, 4.6))
    im = ax.imshow(table[:, :, 0], aspect="auto", cmap="viridis", vmin=0.0, vmax=1.0)
    ax.set_xticks(np.arange(len(scenarios)))
    ax.set_xticklabels(scenarios, rotation=90, fontsize=7)
    ax.set_yticks(np.arange(len(names)))
    ax.set_yticklabels(names, fontsize=8)
    ax.set_title("Success rate per design and scenario")
    fig.colorbar(im, ax=ax, label="success rate")
    save(fig, "ddo_success_heatmap")


def draw_ranking(names, scores, mbo_scores, order):
    fig, ax = plt.subplots(figsize=(7.5, 4.6))
    x = np.arange(len(names))
    ax.bar(x - 0.2, scores[order], width=0.4, color="tab:red",
           label="MAVF over model-based and measured attributes")
    ax.bar(x + 0.2, mbo_scores[order], width=0.4, color="0.6",
           label="MAVF over the model-based attributes alone")
    ax.set_xticks(x)
    ax.set_xticklabels([names[k] for k in order], rotation=90, fontsize=8)
    ax.set_ylabel("MAVF score")
    ax.set_ylim(0.0, 1.2)
    ax.set_title("Ranking before and after the simulation campaign")
    ax.legend(loc="upper left", frameon=False, fontsize=8)
    save(fig, "ddo_mavf_ranking")


def draw_pareto(designs, names, order):
    metrics = np.loadtxt(data / "full_enumeration_4met.csv", delimiter=",")
    mask, idx = non_dominated(metrics, [-1, -1, -1, -1])
    all_subsets = subsets()
    row_of = {s: i for i, s in enumerate(all_subsets)}
    slot = {n: i for i, n in enumerate(sens.NAMES)}
    rows = np.array([row_of[tuple(sorted(slot[n] for n in designs[d]))] for d in names])

    fig, ax = plt.subplots(figsize=(6.4, 4.6))
    ax.scatter(metrics[:, 0], -metrics[:, 3], s=2, color="0.82", label="all designs")
    ax.scatter(metrics[idx, 0], -metrics[idx, 3], s=12, color="tab:red",
               label="model-based frontier")
    ax.scatter(metrics[rows, 0], -metrics[rows, 3], s=26, color="tab:blue",
               label="in the campaign")
    top = rows[order[:3]]
    ax.scatter(metrics[top, 0], -metrics[top, 3], s=110, facecolor="none",
               edgecolor="black", linewidth=1.4, label="top three after the campaign")
    ax.set_xlabel("cost [$]")
    ax.set_ylabel("effective coverage [m^3]")
    ax.set_title("Where the campaign's winners sit in the design space")
    ax.legend(loc="lower right", frameon=False, fontsize=8)
    save(fig, "ddo_pareto_scatter")


# ------------------------------------------------------------------

def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--url", default=ddo_api.DEFAULT_URL, help="the PERFECT server")
    p.add_argument("--submit", action="store_true", help="create and run the campaign")
    p.add_argument("--collect", action="store_true", help="read it back and rank")
    p.add_argument("--wait", type=float, default=1800.0, help="seconds to wait for the trials")
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
