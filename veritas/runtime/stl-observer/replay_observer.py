"""Run the observer's monitors over a recorded CSV instead of a live ROS 2 graph.

Same YAML spec and the same `Monitor` objects as `stl_observer_node.py`, so an obligation that
fires here fires there.  The CSV needs a time column -- `time` or `t` -- and one column per
signal named as in the spec; columns the spec does not mention are ignored.  The range
trajectories written by the Isaac Sim range trial script have the header
`t,x,y,z,roll,pitch,yaw,v`, which `specs/range_safety.yaml` is written against.

    uv run python runtime/stl-observer/replay_observer.py trace.csv --spec specs/agr_safety.yaml

The trace is sampled onto the spec's `rate` the way the node samples the live topics: each
monitor step takes the recorded sample nearest that instant, so a trace recorded at 60 Hz and
a spec that samples at 20 Hz agree on what a bound of "20 seconds" means.  A trace whose own
period already matches the spec's is passed through sample for sample.

Several traces can be given at once.  With `--out` the tool then writes a verdict table --
one row per trace, the worst robustness and the verdict of every obligation -- as
`verdicts.csv` and `verdicts.md`, and the figure pair `robustness.svg` / `robustness.pdf`
with one panel per obligation and one line per trace.  `--points` names a campaign table
whose `trajectory` column identifies each trace, and `--point-columns` says which of its
columns to carry into the verdict row, so the table says which design point each trace came
from.
"""

import argparse
import csv
import os
import sys

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from monitors import load_spec  # noqa: E402

TIME_COLUMNS = ["time", "t"]


def read_csv(path):
    with open(path, newline="") as f:
        rows = list(csv.DictReader(f))
    cols = rows[0].keys() if rows else []
    return {c: [float(r[c]) for r in rows] for c in cols}


def time_column(trace):
    """The name of the trace's time column, or None."""
    return next((c for c in TIME_COLUMNS if c in trace), None)


def resample(trace, rate):
    """Put the trace on the spec's sampling grid, each step taking the nearest recorded sample."""
    key = time_column(trace)
    if key is None:
        return trace
    t = np.asarray(trace[key], dtype=float)
    if t.size < 2:
        return trace
    # the grid stops at the last instant the trace covers; the tolerance keeps a trace whose
    # own period already matches the spec's from losing its last sample to floating point
    span = int(np.floor((t[-1] - t[0]) * rate + 1e-6))
    grid = t[0] + np.arange(span + 1) / rate
    j = np.clip(np.searchsorted(t, grid), 1, t.size - 1)
    nearest = np.where(np.abs(t[j - 1] - grid) <= np.abs(t[j] - grid), j - 1, j)
    return {c: np.asarray(v, dtype=float)[nearest] for c, v in trace.items()}


def replay(spec_path, csv_path):
    """Feed the trace through every monitor. Returns {name: dict with rho, violated, first}."""
    rate, monitors, _ = load_spec(spec_path)
    trace = resample(read_csv(csv_path), rate)
    n = len(next(iter(trace.values()))) if trace else 0
    out = {}
    for m in monitors:
        missing = [s for s in m.signals if s not in trace]
        if missing:
            out[m.name] = {"skipped": missing}
            continue
        rho, viol = [], []
        # RTAMT's online monitor is a stream: it takes one sample per update() call and there is
        # no array-at-once entry point for it, so this steps over samples by construction.
        for k in range(n):
            r, v = m.step({s: trace[s][k] for s in m.signals})
            rho.append(r)
            viol.append(v)
        first = next((i for i, v in enumerate(viol) if v), None)
        out[m.name] = {
            "rho": rho,
            "violated": viol,
            "first_violation_index": first,
            "first_violation_time": None if first is None else first * m.period,
            "requirement": m.requirement,
            "formula": m.formula,
            "period": m.period,
            "warmup": m.warmup,
        }
    return out


def read_points(path, columns):
    """A campaign table keyed by the file name in its `trajectory` column."""
    with open(path, newline="") as f:
        rows = list(csv.DictReader(f))
    return {os.path.basename(r.get("trajectory", "")): {c: r.get(c, "") for c in columns}
            for r in rows}


def verdict_table(spec_path, paths, points=None, point_columns=()):
    """One row per trace: every obligation's worst robustness, verdict and first violation.

    The worst robustness is the minimum of the monitor's output over the run, which for a
    `historically` obligation is its final value and for a windowed one is the hardest instant
    the window ever saw.  Samples inside the monitor's `warmup` are left out of that minimum:
    the monitor does not raise a violation there because its window is not yet full, so its
    robustness there is not a verdict about the run either.  Returns (monitor names, rows,
    replayed traces).
    """
    rate, monitors, _ = load_spec(spec_path)
    names = [m.name for m in monitors]
    rows, traces = [], []
    for path in paths:
        res = replay(spec_path, path)
        trace = resample(read_csv(path), rate)
        stem = os.path.basename(path)
        row = {"trace": stem}
        if points is not None:
            row.update(points.get(stem, {c: "" for c in point_columns}))
        for name in names:
            r = res[name]
            rho = np.asarray(r.get("rho", []), dtype=float)
            first = r.get("first_violation_time")
            judged = np.arange(rho.size) * r.get("period", 0.0) >= r.get("warmup", 0.0)
            row[name + "_rho"] = round(float(rho[judged].min()), 4) if judged.any() else ""
            row[name + "_verdict"] = ("skipped" if "skipped" in r
                                      else "violated" if first is not None else "satisfied")
            row[name + "_first_violation_s"] = "" if first is None else round(first, 2)
        rows.append(row)
        traces.append((stem, trace, res))
    return names, rows, traces


def write_verdicts(names, rows, point_columns, out_dir):
    """`verdicts.csv` with a column per number, `verdicts.md` with a column per obligation."""
    os.makedirs(out_dir, exist_ok=True)
    fields = (["trace"] + list(point_columns)
              + [n + s for n in names for s in ("_rho", "_verdict", "_first_violation_s")])
    csv_path = os.path.join(out_dir, "verdicts.csv")
    with open(csv_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)

    head = ["trace"] + list(point_columns) + names
    lines = ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    for r in rows:
        cells = [r["trace"]] + [str(r[c]) for c in point_columns]
        for n in names:
            if r[n + "_verdict"] == "violated":
                cells.append("violated at " + str(r[n + "_first_violation_s"])
                             + " s, worst rho " + str(r[n + "_rho"]))
            else:
                cells.append("satisfied, worst rho " + str(r[n + "_rho"]))
        lines.append("| " + " | ".join(cells) + " |")
    md_path = os.path.join(out_dir, "verdicts.md")
    open(md_path, "w").write("\n".join(lines) + "\n")
    return csv_path, md_path


def figure(names, traces, out_dir):
    """Robustness over time, one panel per obligation and one line per trace."""
    fig, axes = plt.subplots(len(names), 1, sharex=True, figsize=(9.0, 2.2 * len(names)))
    axes = np.atleast_1d(axes)
    for ax, name in zip(axes, names):
        worst = 0.0
        for stem, trace, res in traces:
            key = time_column(trace)
            rho = np.asarray(res[name].get("rho", []), dtype=float)
            t = np.asarray(trace[key], dtype=float)[:rho.size] if key else np.arange(rho.size)
            ax.plot(t, rho, linewidth=1, label=os.path.splitext(stem)[0])
            worst = min(worst, float(rho.min()) if rho.size else 0.0)
        if worst < -1.0:
            # one run off the scale of the others (a robot on its side) flattens every other
            # line against zero on a linear axis
            ax.set_yscale("symlog", linthresh=0.1)
        ax.axhline(0.0, color="k", linestyle="--", linewidth=0.8)
        warmup = max(res[name].get("warmup", 0.0) for _, _, res in traces)
        if warmup > 0:
            ax.axvspan(0.0, warmup, color="0.9", zorder=0)
        ax.set_ylabel(name, fontsize=9)
        ax.tick_params(labelsize=8)
    axes[0].legend(fontsize=7, loc="upper left", bbox_to_anchor=(1.01, 1.0), borderaxespad=0)
    axes[-1].set_xlabel("monitor time [s]", fontsize=9)
    fig.tight_layout()
    svg = os.path.join(out_dir, "robustness.svg")
    pdf = os.path.join(out_dir, "robustness.pdf")
    fig.savefig(svg)
    fig.savefig(pdf)
    plt.close(fig)
    return svg, pdf


def main():
    p = argparse.ArgumentParser()
    p.add_argument("csv", nargs="+")
    p.add_argument("--spec", default=os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                                  "specs", "agr_safety.yaml"))
    p.add_argument("--every", type=int, default=20, help="print one row every N samples")
    p.add_argument("--out", help="write the verdict table and the figure pair here")
    p.add_argument("--points", help="a campaign table whose `trajectory` column names the traces")
    p.add_argument("--point-columns", default="",
                   help="comma-separated columns of --points to carry into the verdict row")
    a = p.parse_args()

    point_columns = [c for c in a.point_columns.split(",") if c]
    points = read_points(a.points, point_columns) if a.points else None

    if a.out:
        names, rows, traces = verdict_table(a.spec, a.csv, points, point_columns)
        csv_path, md_path = write_verdicts(names, rows, point_columns, a.out)
        svg, pdf = figure(names, traces, a.out)
        for r in rows:
            print(r["trace"] + ": " + ", ".join(
                n + " " + r[n + "_verdict"] + " (rho " + str(r[n + "_rho"]) + ")" for n in names))
        for f in (csv_path, md_path, svg, pdf):
            print("wrote " + f)
        return

    for path in a.csv:
        print_trace(a.spec, path, a.every)


def print_trace(spec_path, csv_path, every):
    rate, _, _ = load_spec(spec_path)
    res = replay(spec_path, csv_path)
    trace = resample(read_csv(csv_path), rate)
    key = time_column(trace)
    t = trace[key] if key else None
    for name, r in res.items():
        print()
        if "skipped" in r:
            print(name + ": skipped, the trace has no column for " + str(r["skipped"]))
            continue
        print(name + " [" + r["requirement"] + "]  " + r["formula"])
        for k in range(0, len(r["rho"]), every):
            stamp = round(float(t[k]), 2) if t is not None else k
            print("  t " + str(stamp) + "  rho " + str(round(r["rho"][k], 4))
                  + ("  VIOLATION" if r["violated"][k] else ""))
        if r["first_violation_index"] is None:
            print("  no violation over " + str(len(r["rho"])) + " samples")
        else:
            k = r["first_violation_index"]
            print("  first violation at sample " + str(k) + ", monitor time "
                  + str(round(r["first_violation_time"], 2)) + " s, rho " + str(round(r["rho"][k], 4)))


if __name__ == "__main__":
    main()
