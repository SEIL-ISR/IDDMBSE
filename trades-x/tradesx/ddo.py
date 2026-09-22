"""Data-driven optimization campaign driver for TRADES-X.

Takes the designs that survived the model-based stage and a grid of start/goal
positions, and emits the PERFECT CLI command sequence that creates the designs,
the environments and the cross product of experiments, then enqueues them.

Ported from examples/SEILR1/robustness.bash on the upstream GitLab branch
`tradesx-demo-redux`. That script called `environments create` and
`simulations create/run`; PERFECT has since renamed the simulations blueprint to
`experiments` and replaced the positional `environments create` with
`environments create_templates_from_file` plus
`environments create_from_template`. The sequence below uses the current names,
which match perfect/examples/isaacsim-carter/load.bash.

--dry-run prints the commands and stops. --execute actually runs them, and that
needs a running PERFECT stack (Redis, an RQ worker, the experiment runner and
the Flask server); this module starts none of them.

A design id is the decimal encoding of the sensor-selection bit vector that the
MBO stage produces: in trades-x/mbo/src/mbo.jl,
`evalpoly(2, reverse(design_id))`, so sensor slot i of n carries weight
2**(n - i) and becomes PERFECT component id i. Design 4234 over 13 slots decodes
to components 1 6 10 12, which is the first line of robustness.bash.
"""

import argparse
import shlex
import subprocess
import sys

import numpy as np

PERFECT_CMD = ["python", "-m", "flask", "--app", "perfect.app"]
DEFAULT_TEMPLATE_FILE = "navigate_to_goal_pose.json"


def design_components(design_id, n_slots=13):
    """Component ids (1-based) selected by a decimal design id."""
    weights = 2 ** np.arange(n_slots - 1, -1, -1)
    bits = (design_id & weights) > 0
    return (np.flatnonzero(bits) + 1).tolist()


def grid_points(spec, lo, hi):
    """Parse a 'WxH' grid spec into x and y coordinate vectors."""
    w, _, h = spec.lower().partition("x")
    nx, ny = int(w), int(h)
    if nx < 1 or ny < 1:
        raise ValueError("grid must be at least 1x1")
    return np.linspace(lo[0], hi[0], nx), np.linspace(lo[1], hi[1], ny)


def campaign_commands(designs, grid, tag, template_id, template_file,
                      components_file=None, n_slots=13, reset_db=True,
                      x_range=(5.0, 7.0), y_range=(2.0, 4.0),
                      start_grid=None, x_start_range=(0.0, 1.0),
                      y_start_range=(0.0, 1.0), run=True):
    cmds = []
    if reset_db:
        cmds.append(PERFECT_CMD + ["db", "init"])
        cmds.append(PERFECT_CMD + ["db", "migrate", "-m", "Initial migration."])
        cmds.append(PERFECT_CMD + ["db", "upgrade"])
    if components_file:
        cmds.append(PERFECT_CMD + ["components", "load_component_implementations", components_file])
    else:
        cmds.append(PERFECT_CMD + ["components", "load_components"])

    for d in designs:
        parts = [str(c) for c in design_components(d, n_slots)]
        cmds.append(PERFECT_CMD + ["designs", "create"] + parts + ["--name", str(d), "--tag", tag])

    cmds.append(PERFECT_CMD + ["environments", "create_templates_from_file", template_file])

    gx, gy = grid_points(grid, (x_range[0], y_range[0]), (x_range[1], y_range[1]))
    if start_grid:
        sx, sy = grid_points(start_grid, (x_start_range[0], y_start_range[0]),
                             (x_start_range[1], y_start_range[1]))
    else:
        sx, sy = np.array([np.nan]), np.array([np.nan])

    for ax in sx:
        for ay in sy:
            for bx in gx:
                for by in gy:
                    kwargs = []
                    name = []
                    if start_grid:
                        kwargs += ["x_start:=" + str(round(float(ax), 3)),
                                   "y_start:=" + str(round(float(ay), 3))]
                        name.append("start " + str(round(float(ax), 3)) + "," + str(round(float(ay), 3)))
                    kwargs += ["x_goal:=" + str(round(float(bx), 3)),
                               "y_goal:=" + str(round(float(by), 3))]
                    name.append("goal " + str(round(float(bx), 3)) + "," + str(round(float(by), 3)))
                    cmds.append(PERFECT_CMD + ["environments", "create_from_template", str(template_id)]
                                + kwargs + ["--name", "; ".join(name), "--tag", tag])

    cmds.append(PERFECT_CMD + ["experiments", "create", tag, tag, "--tag", tag])
    if run:
        cmds.append(PERFECT_CMD + ["experiments", "run", tag])
    return cmds


def main(argv=None):
    p = argparse.ArgumentParser(description="Emit or run a PERFECT DDO campaign")
    p.add_argument("--designs", required=True, help="comma-separated design ids from the MBO stage")
    p.add_argument("--grid", required=True, help="goal grid, e.g. 3x3")
    p.add_argument("--start-grid", help="optional start grid; needs a template with $x_start/$y_start")
    p.add_argument("--tag", default="tradesx")
    p.add_argument("--template-id", type=int, default=1)
    p.add_argument("--template-file", default=DEFAULT_TEMPLATE_FILE)
    p.add_argument("--components-file", help="component implementations JSON; default loads the built-in library")
    p.add_argument("--slots", type=int, default=13, help="number of sensor slots the design ids encode")
    p.add_argument("--no-reset", action="store_true", help="keep the existing database")
    p.add_argument("--no-run", action="store_true", help="create experiments but do not enqueue them")
    p.add_argument("--dry-run", action="store_true", help="print the commands and stop")
    p.add_argument("--execute", action="store_true", help="run the commands (needs a running PERFECT stack)")
    a = p.parse_args(argv)

    designs = [int(s) for s in a.designs.split(",") if s.strip()]
    cmds = campaign_commands(designs, a.grid, a.tag, a.template_id, a.template_file,
                             components_file=a.components_file, n_slots=a.slots,
                             reset_db=not a.no_reset, start_grid=a.start_grid,
                             run=not a.no_run)

    if a.execute and not a.dry_run:
        for c in cmds:
            print(shlex.join(c))
            r = subprocess.run(c)
            if r.returncode != 0:
                print("command failed with code " + str(r.returncode), file=sys.stderr)
                return r.returncode
        return 0

    for c in cmds:
        print(shlex.join(c))
    return 0


if __name__ == "__main__":
    sys.exit(main())
