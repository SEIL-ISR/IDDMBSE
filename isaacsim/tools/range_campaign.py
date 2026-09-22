"""Turn a design of experiments over the test range into a PERFECT campaign.

    python range_campaign.py --plan
    python range_campaign.py --submit  --project-root <perfect>/examples/isaacsim-range
    python range_campaign.py --collect --out results/campaign.csv
    python range_campaign.py --plot    --out results/campaign.csv

One grid point is one environment: an obstacle density, a slope target, a
friction pair, a restitution and a seed. One robot variant is one design. The
grid is the cross product, plus whatever `--extra` adds.

`--submit` does the part only the Flask CLI can do -- create the database, load
the component implementations, create the designs, load the environment
template and create one environment per grid point -- and then goes through
`/api/v1`: one POST per grid point creates the experiment and enqueues its
trial. It then waits, bounded by `--timeout`, until every trial has reached a
terminal state, and prints the state of each.

`--collect` reads the trials back through the same API. Every metric the
experiment relayed arrives as an update row; the last value of each name is the
trial's value, and one row per trial goes into the CSV.

`--plot` writes two figure pairs (SVG and PDF) beside the CSV: the metrics
against obstacle density, one line per slope setting, and the trajectories over
the terrain.

Nothing here starts a PERFECT stack. Bring one up first -- Redis, an RQ worker,
the experiment runner and the Flask server -- as the example's README describes.
"""

import argparse
import csv
import itertools
import json
import os
import pathlib
import shlex
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request

# numpy and matplotlib are imported where they are used, not here: --submit runs
# in the PERFECT environment, which carries neither, while --collect and --plot
# run in this directory's own environment, which carries both.

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent

PERFECT_PYTHON = os.environ.get("PERFECT_PYTHON") or sys.executable
PERFECT_CMD = [PERFECT_PYTHON, "-m", "flask", "--app", "perfect.app"]
DEFAULT_API = "http://127.0.0.1:5001/api/v1"
DEFAULT_TEMPLATE = "templates/contested_terrain.json"
TERMINAL = ("SUCCESSFUL", "ERRORED", "CANCELLED", "TIMED_OUT")

# The order the CSV columns come out in. Anything else the trial relayed is
# appended after these, sorted, so a new metric does not need a code change.
LEAD_COLUMNS = ["trial_id", "experiment_id", "design", "environment", "state",
                "obstacle_density", "max_slope_deg", "friction_static",
                "friction_dynamic", "restitution", "seed", "duration_s",
                "distance_m", "mean_speed_mps", "max_pitch_deg", "mean_pitch_deg",
                "max_roll_deg", "mean_roll_deg", "max_climb_m",
                "obstacle_encounters", "stuck", "unstable", "max_speed_mps",
                "wall_per_sim_s", "prim_count"]


# ------------------------------------------------------------------
# the grid

def parse_list(text, cast=float):
    return [cast(v) for v in str(text).split(",") if str(v).strip() != ""]


def parse_slopes(text):
    """Slope targets; 'authored' keeps the terrain's own height."""
    out = []
    for v in str(text).split(","):
        v = v.strip()
        if not v:
            continue
        out.append("authored" if v.lower() in ("authored", "none") else float(v))
    return out


def parse_frictions(text):
    return [tuple(float(x) for x in pair.split("/")) for pair in str(text).split(",") if pair.strip()]


def expand(densities, slopes, frictions, restitutions, seeds, duration):
    """The cross product, as one dict per grid point."""
    points = []
    for density, slope, friction, restitution, seed in itertools.product(
            densities, slopes, frictions, restitutions, seeds):
        points.append({
            "obstacle_density": density,
            "max_slope_deg": slope,
            "friction_static": friction[0],
            "friction_dynamic": friction[1],
            "restitution": restitution,
            "seed": int(seed),
            "duration_s": duration,
        })
    return points


def point_name(point):
    slope = point["max_slope_deg"]
    return "density %s, slope %s, friction %s/%s, seed %s" % (
        point["obstacle_density"], slope,
        point["friction_static"], point["friction_dynamic"], point["seed"])


def dedupe(points):
    seen = {}
    for p in points:
        seen.setdefault(point_name(p), p)
    return list(seen.values())


# ------------------------------------------------------------------
# the commands only the Flask CLI can run

def setup_commands(points, robots, tag, template_file=DEFAULT_TEMPLATE,
                   components_file="components.json", reset_db=True, template_id=1):
    cmds = []
    if reset_db:
        cmds.append(PERFECT_CMD + ["db", "init"])
        cmds.append(PERFECT_CMD + ["db", "migrate", "-m", "Initial migration."])
        cmds.append(PERFECT_CMD + ["db", "upgrade"])
    cmds.append(PERFECT_CMD + ["components", "load_component_implementations", components_file])
    for robot in robots:
        cmds.append(PERFECT_CMD + ["designs", "create", robot, "-i", "--name", robot, "--tag", tag])
    cmds.append(PERFECT_CMD + ["environments", "create_templates_from_file", template_file])
    for point in points:
        kwargs = ["%s:=%s" % (k, v) for k, v in point.items()]
        cmds.append(PERFECT_CMD + ["environments", "create_from_template", str(template_id)]
                    + kwargs + ["--name", point_name(point), "--tag", tag])
    return cmds


def run_commands(cmds, cwd, env=None):
    for cmd in cmds:
        print(shlex.join(cmd))
        done = subprocess.run(cmd, cwd=cwd, env=env)
        if done.returncode != 0:
            raise SystemExit("command failed with code %d" % done.returncode)


# ------------------------------------------------------------------
# the API

def http_get(url):
    with urllib.request.urlopen(url, timeout=30) as r:
        return json.loads(r.read().decode())


def http_post(url, body):
    request = urllib.request.Request(
        url, data=json.dumps(body).encode(), method="POST",
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=30) as r:
        return json.loads(r.read().decode())


def experiment_payload(design_id, environment_id, tag):
    return {"design_ids": [design_id], "environment_ids": [environment_id],
            "tag": tag, "run": True}


def submit(api, points, robots, tag, get=http_get, post=http_post):
    """One experiment per (robot, grid point). Returns the created records."""
    designs = {d["name"]: d["id"] for d in get(api + "/designs")}
    environments = {e["name"]: e["id"] for e in get(api + "/environments")}
    created = []
    for robot, point in itertools.product(robots, points):
        name = point_name(point)
        if robot not in designs:
            raise SystemExit("no design named %r; run the setup commands first" % robot)
        if name not in environments:
            raise SystemExit("no environment named %r; run the setup commands first" % name)
        reply = post(api + "/experiments",
                     experiment_payload(designs[robot], environments[name], tag))
        record = reply["experiments"][0]
        record["design"] = robot
        record["environment"] = name
        created.append(record)
        print("experiment %s trial %s  %s  %s"
              % (record["experiment_id"], record["trial_ids"], robot, name))
    return created


def states(api, experiment_ids, get=http_get):
    return {i: (get(api + "/experiments/%d" % i)["last_trial_state"] or "") for i in experiment_ids}


def wait_for(api, experiment_ids, timeout, period=15.0, get=http_get, sleep=time.sleep):
    """Bounded wait until every experiment's last trial is in a terminal state."""
    deadline = time.time() + timeout
    while True:
        current = states(api, experiment_ids, get=get)
        done = sum(1 for s in current.values() if any(t in s for t in TERMINAL))
        print("%d/%d trials finished" % (done, len(experiment_ids)), flush=True)
        if done == len(experiment_ids) or time.time() >= deadline:
            return current
        sleep(period)


# ------------------------------------------------------------------
# collecting

def trial_metrics(updates):
    """The last value of every relayed name, from a trial's update rows."""
    metrics = {}
    for u in updates:
        data = u.get("data", u)
        name = data.get("update")
        if name in (None, "init_age", "start_age", "state", "uri"):
            continue
        metrics[name] = data.get("data")
    return metrics


def environment_knobs(specification):
    knobs = dict(specification.get("doe", {}))
    knobs["duration_s"] = specification.get("drive", {}).get("duration_s")
    return knobs


def collect(api, get=http_get, updates_limit=5000):
    rows = []
    for summary in get(api + "/experiments"):
        experiment = get(api + "/experiments/%d" % summary["id"])
        for trial in experiment["trials"]:
            detail = get(api + "/trials/%d?updates=%d" % (trial["id"], updates_limit))
            row = {"trial_id": trial["id"], "experiment_id": experiment["id"],
                   "design": experiment["design"]["name"],
                   "environment": experiment["environment"]["name"],
                   "state": (trial["state"] or "").replace("TrialState.", "")}
            row.update(environment_knobs(experiment["environment"]["specification"]))
            row.update(trial_metrics(detail["updates"]))
            rows.append(row)
    return rows


def copy_trajectories(rows, dest):
    """Bring each trial's pose trajectory next to the campaign table."""
    dest = pathlib.Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    for row in rows:
        source = pathlib.Path(str(row.get("run_dir", ""))) / "trajectory.csv"
        if not source.exists():
            continue
        target = dest / ("trial_%s.csv" % row["trial_id"])
        shutil.copyfile(source, target)
        row["trajectory"] = "%s/%s" % (dest.name, target.name)
    return rows


def strip_machine_paths(row):
    """The table names files by run directory, never by where the run happened."""
    if row.get("run_dir"):
        row["run_dir"] = pathlib.PurePath(str(row["run_dir"])).name
    for key in ("design_point", "layer"):
        if row.get(key):
            path = pathlib.PurePath(str(row[key]))
            row[key] = str(pathlib.PurePath(path.parent.name) / path.name)
    return row


def trajectory_path(row, base):
    """Where this row's trajectory is: the shipped copy, else the run directory."""
    if row.get("trajectory"):
        return pathlib.Path(base) / str(row["trajectory"])
    return pathlib.Path(str(row.get("run_dir", ""))) / "trajectory.csv"


def write_csv(rows, path):
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    extra = sorted({k for r in rows for k in r} - set(LEAD_COLUMNS))
    columns = LEAD_COLUMNS + extra
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for r in rows:
            writer.writerow(r)
    return columns


def read_csv(path):
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


# ------------------------------------------------------------------
# plotting

def column(rows, name, cast=float, missing=None):
    import numpy as np
    missing = np.nan if missing is None else missing
    values = [r.get(name) for r in rows]
    return np.array([missing if v in (None, "", "None") else cast(v) for v in values])


def plot_metrics(rows, out):
    import numpy as np
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    density = column(rows, "obstacle_density")
    slope = np.array([str(r.get("max_slope_deg")) for r in rows])
    distance = column(rows, "distance_m")
    pitch = column(rows, "max_pitch_deg")

    fig, axes = plt.subplots(1, 2, figsize=(9, 3.6))
    for label in sorted(set(slope)):
        take = slope == label
        order = np.argsort(density[take])
        for ax, y in zip(axes, (distance, pitch)):
            ax.plot(density[take][order], y[take][order], marker="o", label="slope " + label)
    axes[0].set_ylabel("distance travelled (m)")
    axes[1].set_ylabel("max pitch (deg)")
    for ax in axes:
        ax.set_xlabel("obstacle density (fraction of footprint)")
        ax.grid(alpha=0.3)
    axes[0].legend(fontsize=8)
    fig.tight_layout()
    save(fig, out)
    return out


def plot_trajectories(rows, out, terrain=None, base="."):
    import numpy as np
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(6, 5.6))
    if terrain is not None:
        (xlo, xhi), (ylo, yhi) = terrain.bounds()
        # world x decreases with the row index and world y with the column
        # index, so both axes are flipped before the array is transposed into
        # the (y, x) order imshow wants.
        h = terrain.h[::-1, ::-1].T[::8, ::8]
        ax.imshow(h, origin="lower", extent=(xlo, xhi, ylo, yhi),
                  cmap="Greys", alpha=0.6, aspect="equal")

    density = column(rows, "obstacle_density")
    lo, hi = np.nanmin(density), np.nanmax(density)
    cmap = plt.get_cmap("viridis")
    dashes = ["-", "--", ":", "-."]
    slopes = sorted({str(r.get("max_slope_deg")) for r in rows})
    x0 = y0 = None
    for row, d in zip(rows, density):
        path = trajectory_path(row, base)
        if not path.exists():
            continue
        t = np.loadtxt(path, delimiter=",", skiprows=1)
        shade = cmap(0.0 if hi == lo else 0.85 * (d - lo) / (hi - lo))
        style = dashes[slopes.index(str(row.get("max_slope_deg"))) % len(dashes)]
        ax.plot(t[:, 1], t[:, 2], style, color=shade, linewidth=1.5,
                label="density %s, slope %s" % (row.get("obstacle_density"), row.get("max_slope_deg")))
        x0, y0 = t[0, 1], t[0, 2]
    if x0 is not None:
        ax.plot([x0], [y0], marker="*", markersize=12, color="crimson")
        ax.set_xlim(x0 - 12, x0 + 12)
        ax.set_ylim(y0 - 12, y0 + 12)
    ax.set_xlabel("x (m)")
    ax.set_ylabel("y (m)")
    ax.legend(fontsize=7, loc="upper left")
    fig.tight_layout()
    save(fig, out)
    return out


def save(fig, out):
    out = pathlib.Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out.with_suffix(".svg"))
    fig.savefig(out.with_suffix(".pdf"))


# ------------------------------------------------------------------

def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--densities", default="0.1,0.4,0.8")
    p.add_argument("--slopes", default="15,authored")
    p.add_argument("--frictions", default="0.6/0.5", help="static/dynamic pairs")
    p.add_argument("--restitutions", default="0.1")
    p.add_argument("--seeds", default="7")
    p.add_argument("--duration", type=float, default=20.0, help="simulated seconds per trial")
    p.add_argument("--robots", default="Carter v2.4", help="comma-separated design names")
    p.add_argument("--extra", help="JSON file with further grid points to append")
    p.add_argument("--tag", default="range")
    p.add_argument("--api", default=DEFAULT_API)
    p.add_argument("--project-root", help="the PERFECT example directory (needed by --submit)")
    p.add_argument("--template-file", default=DEFAULT_TEMPLATE)
    p.add_argument("--components-file", default="components.json")
    p.add_argument("--no-reset", action="store_true", help="keep the existing database")
    p.add_argument("--no-setup", action="store_true", help="skip the CLI setup and only POST")
    p.add_argument("--timeout", type=float, default=3600.0, help="bound on the wait, seconds")
    p.add_argument("--out", default="results/campaign.csv")
    p.add_argument("--plan", action="store_true")
    p.add_argument("--submit", action="store_true")
    p.add_argument("--collect", action="store_true")
    p.add_argument("--plot", action="store_true")
    a = p.parse_args(argv)

    points = expand(parse_list(a.densities), parse_slopes(a.slopes),
                    parse_frictions(a.frictions), parse_list(a.restitutions),
                    parse_list(a.seeds, int), a.duration)
    if a.extra:
        points += json.loads(pathlib.Path(a.extra).read_text())
    points = dedupe(points)
    robots = [r.strip() for r in a.robots.split(",") if r.strip()]

    if a.plan or not (a.submit or a.collect or a.plot):
        print("%d grid points x %d robots = %d trials"
              % (len(points), len(robots), len(points) * len(robots)))
        for point in points:
            print(" ", point_name(point))
        return 0

    if a.submit:
        if not a.project_root:
            raise SystemExit("--submit needs --project-root")
        if not a.no_setup:
            run_commands(setup_commands(points, robots, a.tag, a.template_file,
                                        a.components_file, reset_db=not a.no_reset),
                         cwd=a.project_root)
        created = submit(a.api, points, robots, a.tag)
        final = wait_for(a.api, [c["experiment_id"] for c in created], a.timeout)
        for record in created:
            print("experiment %s  %s  %s  ->  %s"
                  % (record["experiment_id"], record["design"], record["environment"],
                     final[record["experiment_id"]]))

    if a.collect:
        rows = collect(a.api)
        copy_trajectories(rows, pathlib.Path(a.out).parent / "trajectories")
        for row in rows:
            strip_machine_paths(row)
        columns = write_csv(rows, a.out)
        print("wrote %s: %d rows, %d columns" % (a.out, len(rows), len(columns)))

    if a.plot:
        rows = read_csv(a.out)
        sys.path.insert(0, str(HERE))
        import range_doe
        terrain = range_doe.Terrain()
        base = pathlib.Path(a.out).parent
        print("wrote", plot_metrics(rows, base / "campaign_metrics"))
        print("wrote", plot_trajectories(rows, base / "campaign_trajectories", terrain, base))
    return 0


if __name__ == "__main__":
    sys.exit(main())
