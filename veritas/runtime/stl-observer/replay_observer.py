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
"""

import argparse
import csv
import os
import sys

import numpy as np

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
        }
    return out


def main():
    p = argparse.ArgumentParser()
    p.add_argument("csv")
    p.add_argument("--spec", default=os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                                  "specs", "agr_safety.yaml"))
    p.add_argument("--every", type=int, default=20, help="print one row every N samples")
    a = p.parse_args()

    rate, _, _ = load_spec(a.spec)
    res = replay(a.spec, a.csv)
    trace = resample(read_csv(a.csv), rate)
    key = time_column(trace)
    t = trace[key] if key else None
    for name, r in res.items():
        print()
        if "skipped" in r:
            print(name + ": skipped, the trace has no column for " + str(r["skipped"]))
            continue
        print(name + " [" + r["requirement"] + "]  " + r["formula"])
        for k in range(0, len(r["rho"]), a.every):
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
