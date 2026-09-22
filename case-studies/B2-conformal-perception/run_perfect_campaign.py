# The calibration data of this case study, generated as a PERFECT campaign: the
# detector configuration is the design variable, one environment per clutter
# band and seed, one closed-loop episode per trial. The trials write back the
# flat per-detection table with the ground-truth box beside each detection, and
# the split-conformal calibration below is run on what they wrote.
#
#   python run_perfect_campaign.py --submit --url http://127.0.0.1:5001
#   python run_perfect_campaign.py --collect
#   python run_perfect_campaign.py --collect --out <dir>    (tables and figures to <dir>)
#
# --submit loads the three detector implementations, creates the designs, the
# environment template and the environments, then creates one experiment per
# design and environment with a trial enqueued, and waits for them. --collect
# reads the trials back through the same API, writes the detection table and the
# episode table, calibrates on them, sweeps the coverage level and draws the two
# figures.
#
# The PERFECT example behind it is perfect/examples/conformal-calibration, whose
# components.json is the detector library this script loads and whose
# scenario.yaml holds the clutter bands.

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
example = here / ".." / ".." / "perfect" / "examples" / "conformal-calibration"
tradesx_path = here / ".." / ".." / "trades-x"
if str(tradesx_path) not in sys.path:
    sys.path.insert(0, str(tradesx_path))

from tradesx import ddo_api                                    # noqa: E402

from cpnav import campaign, conformal, planner, tradeoff, world    # noqa: E402

results = here / "results" / "perfect"
figures = here / "figures"

TAG = "conformal"

# The grid.
CLUTTER = ["sparse", "nominal", "dense"]
SEEDS = list(range(30))
N_EPISODES = 1

# Trials whose seed is below this calibrate; the rest are held out. The split is
# taken over whole trials, because detections inside one episode are not
# exchangeable with each other.
N_CALIBRATION_SEEDS = 20
CALIBRATION_DETECTOR = "nominal"

ALPHA = 0.10
ALPHAS = [0.30, 0.20, 0.15, 0.10, 0.05, 0.02, 0.01]

# The closed-loop sweep the calibration feeds: fresh arenas, one arm per level.
K_TEST = 200
TEST_CLUTTER = "nominal"
SWEEP_SEED = 20260922
BOOTSTRAP_SEED = SWEEP_SEED + 2

DETECTOR_COLOUR = {"sharp": "#2ca02c", "nominal": "#1f77b4", "degraded": "#d62728"}

ROW_COLUMNS = list(planner.ROW_COLUMNS)
EPISODE_COLUMNS = ["trial_id", "detector", "shift", "clutter", "seed", "episodes",
                   "detections", "collisions", "successes", "stalls",
                   "collision_rate", "mean_length", "mean_waits",
                   "score_mean", "score_max", "coverage_margin"]


def library():
    return json.load(open(example / "components.json"))


def detectors():
    return [c["name"] for c in library()]


def campaign_designs():
    """One design per detector configuration."""
    return {name: [name] for name in detectors()}


def campaign_environments():
    """One environment per clutter band and seed."""
    grid = {}
    for clutter in CLUTTER:
        for seed in SEEDS:
            key = clutter + "-seed" + str(seed)
            grid[key] = {"clutter": clutter, "seed": seed, "n_episodes": N_EPISODES}
    return grid


# ------------------------------------------------------------------
# submit

def do_submit(server, wait_seconds):
    designs = campaign_designs()
    environments = campaign_environments()
    template = json.load(open(example / "environment_template.json"))[0]

    print("detectors:", len(designs), "environments:", len(environments),
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
# the collected tables

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


def detection_table(rows):
    """Every detection of the campaign in one array, with its trial beside it.

    The trial id is the calibration group: one trial is one closed-loop episode,
    and detections inside an episode see the same objects from nearby poses, so
    they are not exchangeable with each other.
    """
    counts = np.array([len(r["rows"]) for r in rows])
    table = np.concatenate([np.asarray(r["rows"], dtype=float).reshape(-1, len(ROW_COLUMNS))
                            for r in rows])
    where = {
        "trial_id": np.repeat([r["trial_id"] for r in rows], counts),
        "detector": np.repeat([r["detector"] for r in rows], counts),
        "clutter": np.repeat([r["clutter"] for r in rows], counts),
        "seed": np.repeat([r["seed"] for r in rows], counts),
    }
    return where, table


def write_detections(where, table, path):
    columns = ["trial_id", "detector", "clutter", "seed"] + ROW_COLUMNS
    labels = list(zip(where["trial_id"].tolist(), where["detector"].tolist(),
                      where["clutter"].tolist(), where["seed"].tolist()))
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(columns)
        for label, values in zip(labels, table.tolist()):
            w.writerow(list(label) + [fmt(v) for v in values])


def write_episodes(rows, path):
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(EPISODE_COLUMNS)
        for r in rows:
            w.writerow([fmt(r.get(c)) for c in EPISODE_COLUMNS])


def write_coverage(table, path):
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["alpha", "target_coverage", "q", "calibration_rows", "holdout_rows",
                    "holdout_coverage", "holdout_coverage_lo", "holdout_coverage_hi"]
                   + ["coverage_" + d for d in detectors()])
        for r in table:
            w.writerow([fmt(v) for v in r])


def write_sweep(alphas, qs, arms, path):
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["alpha", "target_coverage", "q", "collision_rate", "success_rate",
                    "stall_rate", "mean_path_length", "mean_waits"])
        for alpha, q, arm in zip(alphas, qs, arms):
            w.writerow([fmt(alpha), fmt(1.0 - alpha), fmt(q), fmt(arm["collision_rate"]),
                        fmt(arm["success_rate"]), fmt(arm["stall_rate"]),
                        fmt(arm["mean_path_length"]), fmt(arm["mean_waits"])])


# ------------------------------------------------------------------
# the calibration

def scores_of(table, mask):
    truth, detected = table[mask, 6:10], table[mask, 10:14]
    return conformal.scores(detected, truth)


def masks(where):
    """Which detections calibrate, which are held out, and which each detector made."""
    nominal = where["detector"] == CALIBRATION_DETECTOR
    calibration = nominal & (where["seed"] < N_CALIBRATION_SEEDS)
    holdout = nominal & (where["seed"] >= N_CALIBRATION_SEEDS)
    return calibration, holdout, [where["detector"] == d for d in detectors()]


def coverage_table(where, table):
    """One row per coverage level: the quantile it asks for and what it bought."""
    calibration, holdout, by_detector = masks(where)
    cal_scores = scores_of(table, calibration)
    hold_scores = scores_of(table, holdout)
    boot = np.random.default_rng(BOOTSTRAP_SEED)

    qs = [conformal.quantile(cal_scores, a) for a in ALPHAS]
    rows = []
    for alpha, q in zip(ALPHAS, qs):
        lo, hi = conformal.bootstrap_coverage(
            table[holdout, 10:14], table[holdout, 6:10], q,
            where["trial_id"][holdout], boot)
        row = [alpha, 1.0 - alpha, q, int(calibration.sum()), int(holdout.sum()),
               float((hold_scores <= q).mean()), lo, hi]
        row += [float((scores_of(table, m) <= q).mean()) for m in by_detector]
        rows.append(row)
    return rows, qs, cal_scores


def alpha_sweep(qs):
    """The closed loop at each of those quantiles, on arenas the campaign never saw."""
    world.MIN_OBSTACLES, world.MAX_OBSTACLES = band(TEST_CLUTTER)
    rng = np.random.default_rng(SWEEP_SEED)
    boxes, valid, hard = campaign.feasible_worlds(rng, K_TEST)
    arms, _ = tradeoff.sweep(rng, boxes, valid, hard, [0.0] + list(qs))
    return arms[0], arms[1:]


def band(name):
    """How many obstacles a clutter band stands up, out of the example's scenario."""
    bands = yaml.safe_load(open(example / "scenario.yaml"))["bands"]
    return int(bands[name][0]), int(bands[name][1])


def collision_rates(rows):
    """{detector: [collision rate per clutter band]} off the campaign's own episodes."""
    out = {}
    for detector in detectors():
        rates = []
        for clutter in CLUTTER:
            picked = [r for r in rows if r["detector"] == detector and r["clutter"] == clutter]
            collisions = sum(r["collisions"] for r in picked)
            episodes = sum(r["episodes"] for r in picked)
            rates.append(collisions / episodes)
        out[detector] = rates
    return out


def do_collect(server):
    results.mkdir(parents=True, exist_ok=True)
    figures.mkdir(exist_ok=True)

    rows = ddo_api.collect(server, TAG)
    states = sorted({r["state"] for r in rows})
    successful = [r for r in rows if "SUCCESSFUL" in (r["state"] or "")]
    print("trials collected:", len(rows), "states:", states)
    print("SUCCESSFUL trials:", len(successful))

    where, table = detection_table(rows)
    print("episodes:", sum(r["episodes"] for r in rows), "detections:", table.shape[0])
    write_detections(where, table, results / "calibration.csv")
    write_episodes(rows, results / "episodes.csv")

    coverage, qs, cal_scores = coverage_table(where, table)
    write_coverage(coverage, results / "coverage.csv")
    nominal_arm, arms = alpha_sweep(qs)
    write_sweep(ALPHAS, qs, arms, results / "alpha_sweep.csv")

    print_tables(coverage, nominal_arm, arms, rows)
    draw_coverage(where, table, coverage, cal_scores)
    draw_tradeoff(rows, coverage, nominal_arm, arms)
    write_summary(rows, table, coverage, nominal_arm, arms, results / "summary.json")
    print()
    print("results written to", shown(results))
    print("figures written to", shown(figures))
    return len(successful), coverage


def print_tables(coverage, nominal_arm, arms, rows):
    print()
    print("calibrated on", coverage[0][3], "detections of the", CALIBRATION_DETECTOR,
          "detector, held out", coverage[0][4])
    print("alpha  target   q (m)   held-out coverage   90% episode-bootstrap interval"
          + "".join(["   " + d for d in detectors()]))
    for r in coverage:
        print(" ", r[0], "  ", round(r[1], 3), "  ", round(r[2], 3), "  ", round(r[5], 4),
              "  ", round(r[6], 4), round(r[7], 4),
              "  ", "  ".join([str(round(v, 4)) for v in r[8:]]))

    print()
    print("closed loop over", K_TEST, "arenas the campaign never saw")
    print("arm          q (m)  collisions  success  stalls  mean path (m)  mean waits")
    labels = ["nominal"] + ["alpha=" + str(a) for a in ALPHAS]
    for label, arm in zip(labels, [nominal_arm] + list(arms)):
        print(" ", label.ljust(11), round(arm["q"], 3),
              int(round(arm["collision_rate"] * K_TEST)),
              "   ", round(arm["success_rate"], 3),
              "  ", int(round(arm["stall_rate"] * K_TEST)),
              "   ", round(arm["mean_path_length"], 2),
              "   ", round(arm["mean_waits"], 2))

    print()
    print("the campaign's own episodes, collision rate by clutter band")
    print("detector    " + "  ".join([c.rjust(8) for c in CLUTTER]))
    for detector, rates in collision_rates(rows).items():
        print(detector.ljust(12) + "  ".join([str(round(v, 3)).rjust(8) for v in rates]))


def write_summary(rows, table, coverage, nominal_arm, arms, path):
    operating = next(r for r in coverage if r[0] == ALPHA)
    summary = {
        "campaign": {
            "trials": len(rows),
            "episodes": sum(r["episodes"] for r in rows),
            "detections": int(table.shape[0]),
            "detectors": detectors(),
            "clutter_bands": CLUTTER,
            "seeds": len(SEEDS),
            "calibration_detector": CALIBRATION_DETECTOR,
            "calibration_rows": operating[3],
            "holdout_rows": operating[4],
        },
        "operating_point": {
            "alpha": ALPHA,
            "q_m": operating[2],
            "holdout_coverage": operating[5],
            "holdout_coverage_interval": [operating[6], operating[7]],
            "coverage_by_detector": dict(zip(detectors(), operating[8:])),
        },
        "closed_loop": {
            "test_episodes": K_TEST,
            "clutter": TEST_CLUTTER,
            "nominal": nominal_arm,
            "sweep": [dict(arm, alpha=a) for a, arm in zip(ALPHAS, arms)],
        },
        "collision_rate_by_clutter": collision_rates(rows),
    }
    with open(path, "w") as f:
        json.dump(summary, f, indent=2)
        f.write("\n")


# ------------------------------------------------------------------
# figures

def save(fig, stem):
    fig.savefig(figures / (stem + ".svg"))
    fig.savefig(figures / (stem + ".pdf"))
    plt.close(fig)


def draw_coverage(where, table, coverage, cal_scores):
    """What the campaign's detections say: the scores, and the coverage they buy."""
    calibration, _, _ = masks(where)
    clutter = where["clutter"]
    q_main = next(r[2] for r in coverage if r[0] == ALPHA)

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10.5, 4.4))
    edges = np.linspace(float(cal_scores.min()), float(cal_scores.max()), 41)
    for name in CLUTTER:
        ax1.hist(scores_of(table, calibration & (clutter == name)), bins=edges,
                 histtype="step", linewidth=1.4, density=True, label=name + " clutter")
    ax1.axvline(q_main, color="0.2", linestyle="--", linewidth=1.2,
                label="q at alpha = " + str(ALPHA) + ", " + str(round(q_main, 3)) + " m")
    ax1.set_xlabel("nonconformity score (m)")
    ax1.set_ylabel("density")
    ax1.set_title("calibration scores of the " + CALIBRATION_DETECTOR + " detector")
    ax1.legend(fontsize=8)

    target = 1.0 - np.array(ALPHAS)
    ax2.plot([target.min(), 1.0], [target.min(), 1.0], color="0.6", lw=1, ls="--",
             label="target 1 - alpha")
    hold = np.array([r[5] for r in coverage])
    err = np.stack([hold - np.array([r[6] for r in coverage]),
                    np.array([r[7] for r in coverage]) - hold])
    ax2.errorbar(target, hold, yerr=err, fmt="o-", color="tab:blue", capsize=3,
                 label="held-out " + CALIBRATION_DETECTOR + ", 90% episode bootstrap")
    for i, name in enumerate(detectors()):
        if name == CALIBRATION_DETECTOR:
            continue
        ax2.plot(target, [r[8 + i] for r in coverage], "s--", color=DETECTOR_COLOUR[name],
                 label="the " + name + " detector")
    ax2.set_xlabel("target coverage 1 - alpha")
    ax2.set_ylabel("empirical coverage")
    ax2.set_title("coverage on detections the calibration never saw")
    ax2.legend(fontsize=8, loc="lower right")
    fig.suptitle("Conformal calibration on a PERFECT campaign")
    fig.tight_layout()
    save(fig, "perfect_coverage")


def draw_tradeoff(rows, coverage, nominal_arm, arms):
    """What the coverage costs: the campaign's own arm, then the sweep at its quantiles."""
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10.5, 4.4))
    x = np.arange(len(CLUTTER))
    for detector, rates in collision_rates(rows).items():
        ax1.plot(x, rates, "o-", color=DETECTOR_COLOUR[detector], label=detector)
    ax1.set_xticks(x)
    ax1.set_xticklabels(CLUTTER)
    ax1.set_ylim(0.0, 1.05)
    ax1.set_xlabel("clutter band")
    ax1.set_ylabel("collision rate, raw detections")
    ax1.set_title("what the campaign measured")
    ax1.legend(fontsize=8)

    target = 1.0 - np.array(ALPHAS)
    collisions = [a["collision_rate"] for a in arms]
    lengths = [a["mean_path_length"] for a in arms]
    ax2.plot(target, collisions, "o-", color="tab:red", label="collision rate")
    ax2.axhline(nominal_arm["collision_rate"], color="tab:red", lw=1, ls=":",
                label="collision rate, raw detections")
    ax2.set_xlabel("target coverage 1 - alpha")
    ax2.set_ylabel("collision rate over " + str(K_TEST) + " episodes")
    ax2.set_ylim(0.0, max(collisions + [nominal_arm["collision_rate"]]) * 1.15)
    ax3 = ax2.twinx()
    ax3.plot(target, lengths, "s--", color="tab:green", label="mean path length")
    ax3.axhline(nominal_arm["mean_path_length"], color="tab:green", lw=1, ls=":",
                label="mean path length, raw detections")
    ax3.set_ylabel("mean path length (m)")
    ax2.set_title("what the coverage costs")
    lines = ax2.get_lines() + ax3.get_lines()
    ax2.legend(lines, [l.get_label() for l in lines], fontsize=8, loc="center right")
    fig.suptitle("Coverage bought against navigation conservativeness")
    fig.tight_layout()
    save(fig, "perfect_tradeoff")


# ------------------------------------------------------------------

def send_output_to(out):
    """--out: the tables and the figures go to `out` instead of results/perfect and figures/."""
    global results, figures
    results = figures = pathlib.Path(out)
    results.mkdir(parents=True, exist_ok=True)


def shown(path):
    """A path inside this directory relative to it, any other path as it is."""
    return path.relative_to(here) if path.is_relative_to(here) else path


def main(argv=None):
    p = argparse.ArgumentParser(description="the conformal calibration campaign on PERFECT")
    p.add_argument("--url", default=ddo_api.DEFAULT_URL, help="the PERFECT server")
    p.add_argument("--submit", action="store_true", help="create and run the campaign")
    p.add_argument("--collect", action="store_true", help="read it back, calibrate and draw")
    p.add_argument("--wait", type=float, default=2400.0, help="seconds to wait for the trials")
    p.add_argument("--out", help="write the tables and the figures to this directory "
                   "instead of results/perfect and figures/")
    args = p.parse_args(argv)
    if not (args.submit or args.collect):
        p.error("give --submit, --collect, or both")
    if args.out:
        send_output_to(args.out)

    server = ddo_api.Server(args.url)
    if args.submit:
        do_submit(server, args.wait)
    if args.collect:
        do_collect(server)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
