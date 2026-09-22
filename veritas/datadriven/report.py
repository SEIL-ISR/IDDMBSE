"""Failure rates and confidence bounds for a PERFECT campaign, grouped by design and environment.

This is the data-driven module's command-line front end: point it at any PERFECT SQLite
database (or a CSV export of one) and it writes the numbers an assurance argument cites.

    uv run python datadriven/report.py --db path/to/campaign.db --out datadriven/report_out
    uv run python datadriven/report.py --csv campaign.csv --out datadriven/report_out

`--tag` narrows the read to one campaign's experiments, `--group-by design` (or `environment`)
folds the other axis away, and `--failure-metric NAME --failure-below X` decides the outcome
from a per-trial number rather than from the state PERFECT recorded -- a runner that finishes
a trial is saying the simulation ran, which is not the same as the mission going well.

Per (design, environment) group it reports the trial and failure counts, the failure rate,
the exact (Clopper-Pearson) and Wilson intervals, the one-sided exact upper bound, and how
many trials that group would need before its upper bound reaches `--target`.  When the
campaign carries a per-trial number -- `--metric`, by default `robustness`, read out of the
`update` table's JSON payloads or a column of the CSV -- it adds the robustness summary with
the DKW-corrected lower quantile.

Written to `--out`: `report.json`, `report.md`, `report.csv` and the figure pair
`failure_rates.svg` / `failure_rates.pdf` (failure rate per group with its exact interval).

Every number is computed over whole arrays: groups are an index array, and the bound
functions in `campaign_stats.py` broadcast over the per-group counts.
"""

import argparse
import csv as csvlib
import json
import os
import sys

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import campaign_stats as cs  # noqa: E402
import perfect_adapter as pa  # noqa: E402


GROUPINGS = ["design-environment", "design", "environment"]


def group_index(design, environment, by="design-environment"):
    """(design, environment) pairs to a group index array and the list of group labels.

    `by` folds one of the two axes away: `design` puts every environment of a design in one
    group (the column then reads `all`), `environment` does the reverse.
    """
    design = np.asarray(design, dtype=object).astype(str)
    environment = np.asarray(environment, dtype=object).astype(str)
    if by == "design":
        environment = np.full(design.size, "all", dtype=object).astype(str)
    elif by == "environment":
        design = np.full(environment.size, "all", dtype=object).astype(str)
    labels = np.char.add(np.char.add(design, " | "), environment)
    uniq, idx = np.unique(labels, return_inverse=True)
    return idx, [u.split(" | ") for u in uniq]


def summarise(success, design, environment, rho=None, delta=0.05, target=0.05, level=0.05,
              by="design-environment"):
    """Per-group counts, rates and bounds. `success` is True for a successful trial."""
    success = np.asarray(success, dtype=bool)
    idx, groups = group_index(design, environment, by)
    n_groups = len(groups)
    trials = np.bincount(idx, minlength=n_groups)
    failures = np.bincount(idx, weights=(~success).astype(float), minlength=n_groups)
    rate = np.where(trials > 0, failures / np.maximum(trials, 1), np.nan)

    cp_lo, cp_hi = cs.clopper_pearson(failures, trials, delta)
    cp_up = cs.clopper_pearson_upper(failures, trials, delta)
    w_lo, w_hi = cs.wilson(failures, trials, delta)
    needed = cs.trials_for_upper_bound_array(target, delta, failures)

    out = {
        "groups": groups, "index": idx, "trials": trials, "failures": failures.astype(int),
        "failure_rate": rate, "clopper_pearson_lo": cp_lo, "clopper_pearson_hi": cp_hi,
        "clopper_pearson_upper": cp_up, "wilson_lo": w_lo, "wilson_hi": w_hi,
        "trials_for_target": needed, "delta": delta, "target": target, "level": level,
    }
    if rho is not None:
        rho = np.asarray(rho, dtype=float)
        finite = np.isfinite(rho)
        if finite.any():
            out["robustness"] = cs.robustness_stats_by_group(
                rho[finite], idx[finite], n_groups, level=level, delta=delta)
    return out


def read_database(db_path, metric="robustness", tag=None, failure_metric=None):
    c = pa.read_campaign(db_path, experiment_tag=tag)
    rho = pa.read_metric(db_path, c["trial_id"], name=metric)
    outcome = (None if failure_metric is None
               else pa.read_metric(db_path, c["trial_id"], name=failure_metric))
    return c["success"], c["design_name"], c["environment_name"], rho, outcome


def read_csv_column(csv_path, name):
    """One named column of a CSV campaign as floats; an empty cell and a missing column are nan.

    A boolean column written by a Python tool reads `True` / `False`, so those two spellings
    become 1 and 0 and a threshold can be put on them like any other number.
    """
    with open(csv_path, newline="") as f:
        rows = list(csvlib.DictReader(f))
    cells = [("" if r.get(name) is None else str(r[name]).strip()) for r in rows]
    text = np.array(cells, dtype=object).astype(str)
    lowered = np.char.lower(text)
    out = np.full(text.size, np.nan)
    known = ~np.isin(lowered, ["", "true", "false", "nan", "none"])
    out[lowered == "true"] = 1.0
    out[lowered == "false"] = 0.0
    out[known] = text[known].astype(float)
    return out


def read_csv_campaign(csv_path, metric="robustness"):
    c = pa.read_campaign_csv(csv_path, robustness_column=metric)
    n = c["success"].size
    design = c.get("design_name", np.array(["all"] * n, dtype=object))
    environment = c.get("environment_name", np.array(["all"] * n, dtype=object))
    return c["success"], design, environment, c.get("robustness")


ROWS = ["design", "environment", "trials", "failures", "failure_rate",
        "clopper_pearson_lo", "clopper_pearson_hi", "clopper_pearson_upper",
        "wilson_lo", "wilson_hi", "trials_for_target"]
RHO_ROWS = ["rho_n", "rho_mean", "rho_min", "rho_violated", "rho_quantile", "rho_quantile_dkw"]


def table(s):
    """The per-group table as a list of dicts, ready for the CSV and the JSON."""
    rows = []
    for i, (design, environment) in enumerate(s["groups"]):
        r = {"design": design, "environment": environment,
             "trials": int(s["trials"][i]), "failures": int(s["failures"][i]),
             "failure_rate": float(s["failure_rate"][i]),
             "clopper_pearson_lo": float(s["clopper_pearson_lo"][i]),
             "clopper_pearson_hi": float(s["clopper_pearson_hi"][i]),
             "clopper_pearson_upper": float(s["clopper_pearson_upper"][i]),
             "wilson_lo": float(s["wilson_lo"][i]), "wilson_hi": float(s["wilson_hi"][i]),
             "trials_for_target": int(s["trials_for_target"][i])}
        if "robustness" in s:
            b = s["robustness"]
            r.update({"rho_n": int(b["n"][i]), "rho_mean": float(b["mean"][i]),
                      "rho_min": float(b["min"][i]), "rho_violated": float(b["violated"][i]),
                      "rho_quantile": float(b["quantile"][i]),
                      "rho_quantile_dkw": float(b["quantile_dkw"][i])})
        rows.append(r)
    return rows


def write_files(s, rows, source, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    has_rho = "robustness" in s
    conf = str(round(1 - s["delta"], 3))

    json_path = os.path.join(out_dir, "report.json")
    open(json_path, "w").write(json.dumps(
        {"source": source, "delta": s["delta"], "target": s["target"], "level": s["level"],
         "groups": rows}, indent=2, default=str) + "\n")

    csv_path = os.path.join(out_dir, "report.csv")
    fields = ROWS + (RHO_ROWS if has_rho else [])
    with open(csv_path, "w", newline="") as f:
        w = csvlib.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)

    lines = ["# Campaign failure rates", "",
             "source: `" + os.path.basename(source) + "`",
             "confidence " + conf + ", target upper bound " + str(s["target"]), "",
             "| design | environment | trials | failures | rate | exact interval | "
             "Wilson interval | exact upper | trials for target |",
             "|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        lines.append("| " + r["design"] + " | " + r["environment"] + " | "
                     + str(r["trials"]) + " | " + str(r["failures"]) + " | "
                     + str(round(r["failure_rate"], 4)) + " | ["
                     + str(round(r["clopper_pearson_lo"], 4)) + ", "
                     + str(round(r["clopper_pearson_hi"], 4)) + "] | ["
                     + str(round(r["wilson_lo"], 4)) + ", "
                     + str(round(r["wilson_hi"], 4)) + "] | "
                     + str(round(r["clopper_pearson_upper"], 4)) + " | "
                     + str(r["trials_for_target"]) + " |")
    if has_rho:
        lines += ["", "## Post-hoc robustness", "",
                  "| design | environment | n | mean | min | violated | "
                  + str(s["level"]) + " quantile | DKW-corrected |", "|---|---|---|---|---|---|---|---|"]
        for r in rows:
            dkw = ("-inf" if not np.isfinite(r["rho_quantile_dkw"])
                   else str(round(r["rho_quantile_dkw"], 4)))
            lines.append("| " + r["design"] + " | " + r["environment"] + " | " + str(r["rho_n"])
                         + " | " + str(round(r["rho_mean"], 4)) + " | "
                         + str(round(r["rho_min"], 4)) + " | "
                         + str(round(r["rho_violated"], 4)) + " | "
                         + str(round(r["rho_quantile"], 4)) + " | " + dkw + " |")
    md_path = os.path.join(out_dir, "report.md")
    open(md_path, "w").write("\n".join(lines) + "\n")
    return json_path, md_path, csv_path


def figure(s, out_dir):
    """Failure rate per group with its exact interval and the Wilson one, SVG and PDF."""
    x = np.arange(len(s["groups"]))
    rate = s["failure_rate"]
    lo = np.maximum(rate - s["clopper_pearson_lo"], 0)
    hi = np.maximum(s["clopper_pearson_hi"] - rate, 0)
    w_lo = np.maximum(rate - s["wilson_lo"], 0)
    w_hi = np.maximum(s["wilson_hi"] - rate, 0)

    fig, ax = plt.subplots(figsize=(1.6 + 1.5 * len(x), 4.0))
    ax.errorbar(x - 0.06, rate, yerr=np.vstack([lo, hi]), fmt="o", capsize=5,
                label="Clopper-Pearson " + str(round(1 - s["delta"], 3)))
    ax.errorbar(x + 0.06, rate, yerr=np.vstack([w_lo, w_hi]), fmt="s", capsize=5,
                label="Wilson " + str(round(1 - s["delta"], 3)))
    ax.axhline(s["target"], linestyle="--", linewidth=1,
               label="target " + str(s["target"]))
    ax.set_xticks(x)
    # a real campaign's environment name is a whole design point ("density 0.4, slope 25.0,
    # ..."), which runs into its neighbour at this width; break it at its commas instead
    ax.set_xticklabels([(d + "\n" + e).replace(", ", "\n") for d, e in s["groups"]], fontsize=8)
    ax.set_ylabel("failure rate")
    top = min(1.02, 1.2 * max(s["clopper_pearson_hi"].max(), s["wilson_hi"].max(), s["target"]))
    ax.set_ylim(-0.02 * top, top)
    ax.set_xlim(-0.6, len(x) - 0.4)
    ax.legend(fontsize=8)
    fig.tight_layout()
    svg = os.path.join(out_dir, "failure_rates.svg")
    pdf = os.path.join(out_dir, "failure_rates.pdf")
    fig.savefig(svg)
    fig.savefig(pdf)
    plt.close(fig)
    return svg, pdf


def main():
    p = argparse.ArgumentParser(description="failure rates and bounds over a PERFECT campaign")
    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument("--db", help="a PERFECT SQLite database (opened read-only)")
    src.add_argument("--csv", help="a CSV export of a campaign")
    p.add_argument("--out", default=".", help="directory for the report files and the figure")
    p.add_argument("--metric", default="robustness", help="per-trial number to summarise")
    p.add_argument("--tag", help="only the experiments carrying this tag (a database campaign)")
    p.add_argument("--group-by", default="design-environment", choices=GROUPINGS,
                   help="fold the environments of a design, or the designs of an environment,"
                        " into one group")
    p.add_argument("--failure-metric",
                   help="decide the outcome from a per-trial number instead of the state"
                        " PERFECT recorded; needs --failure-below or --failure-above")
    p.add_argument("--failure-below", type=float,
                   help="a trial fails when its --failure-metric is below this")
    p.add_argument("--failure-above", type=float,
                   help="a trial fails when its --failure-metric is above this")
    p.add_argument("--delta", type=float, default=0.05, help="1 - delta is the confidence")
    p.add_argument("--target", type=float, default=0.05, help="failure-rate upper bound to reach")
    p.add_argument("--level", type=float, default=0.05, help="robustness quantile level")
    a = p.parse_args()

    if a.failure_metric and a.failure_below is None and a.failure_above is None:
        p.error("--failure-metric needs --failure-below or --failure-above")

    source = a.db or a.csv
    if a.db:
        success, design, environment, rho, outcome = read_database(
            a.db, a.metric, a.tag, a.failure_metric)
    else:
        success, design, environment, rho = read_csv_campaign(a.csv, a.metric)
        outcome = None if a.failure_metric is None else read_csv_column(a.csv, a.failure_metric)
    if success.size == 0:
        print("no trials in " + source)
        return 1

    if outcome is not None:
        # the criterion replaces PERFECT's trial state: the runner finishing a trial says the
        # simulation ran, not that the mission went well.  A trial the campaign never recorded
        # the number for cannot be judged and drops out.
        judged = np.isfinite(outcome)
        success = np.ones(outcome.size, dtype=bool)
        if a.failure_below is not None:
            success &= outcome >= a.failure_below
        if a.failure_above is not None:
            success &= outcome <= a.failure_above
        dropped = int((~judged).sum())
        success, design, environment = success[judged], design[judged], environment[judged]
        rho = None if rho is None else rho[judged]
        print("outcome from " + a.failure_metric + ": " + str(int((~success).sum()))
              + " of " + str(int(judged.sum())) + " trials count as failures"
              + ("" if dropped == 0 else ", " + str(dropped) + " carried no such number"))

    s = summarise(success, design, environment, rho=rho, by=a.group_by,
                  delta=a.delta, target=a.target, level=a.level)
    rows = table(s)
    json_path, md_path, csv_path = write_files(s, rows, source, a.out)
    svg, pdf = figure(s, a.out)

    print("campaign " + source + ": " + str(int(s["trials"].sum())) + " trials in "
          + str(len(s["groups"])) + " design/environment groups")
    for r in rows:
        line = (r["design"] + " | " + r["environment"] + ": " + str(r["trials"]) + " trials, "
                + str(r["failures"]) + " failures, rate " + str(round(r["failure_rate"], 4))
                + ", exact [" + str(round(r["clopper_pearson_lo"], 4)) + ", "
                + str(round(r["clopper_pearson_hi"], 4)) + "], upper "
                + str(round(r["clopper_pearson_upper"], 4)) + ", "
                + str(r["trials_for_target"]) + " trials for " + str(a.target))
        if "rho_n" in r:
            dkw = ("-inf" if not np.isfinite(r["rho_quantile_dkw"])
                   else str(round(r["rho_quantile_dkw"], 4)))
            line += ("\n  " + a.metric + ": n " + str(r["rho_n"]) + ", mean "
                     + str(round(r["rho_mean"], 4)) + ", min " + str(round(r["rho_min"], 4))
                     + ", violated " + str(round(r["rho_violated"], 4)) + ", quantile "
                     + str(round(r["rho_quantile"], 4)) + ", DKW-corrected " + dkw)
        print(line)
    for f in (json_path, md_path, csv_path, svg, pdf):
        print("wrote " + f)
    return 0


if __name__ == "__main__":
    sys.exit(main())
