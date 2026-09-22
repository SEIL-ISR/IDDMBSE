# How a SysML model binds to PERFECT

This describes the mapping between a SysML model and PERFECT's database, and the two
routes a SysML tool uses to reach a running PERFECT server. It documents what is in the
tree on 2026-09-22; where something is described but not implemented, it says so.

The two halves are:

- **The library mapping** — which SysML element becomes which row in PERFECT's schema
  (`perfect/app/models.py`, `perfect/app/schema/*.json`).
- **The live binding** — how the mk6 SysML model's constraint blocks reach the server,
  through the MATLAB functions in `sysml/workbench/bridge/` and `POST /api/v1/run`.

## The library mapping

PERFECT's schema separates what a part *is* from how a particular stack *runs* it. That is
the same split a SysML model makes between a block with value properties (the datasheet)
and the configuration that realizes it in a build.

| SysML element | PERFECT table | what carries over |
|---|---|---|
| Block with value properties, e.g. a LiDAR datasheet | `Component` | one column per value property. The columns that exist are named in `perfect/app/models.py`: `channels`, `field_of_view_horizontal`, `range_max`, `rotation_rate_max`, `mass`, `power`, `voltage_min/max`, `wavelength` and the rest. A value property with no column has nowhere to go; add a column and a migration, or carry it in the implementation JSON. |
| The stack-specific realization of that block — the ROS 2 node, its parameters, the launch arguments and file edits that instantiate it | `ComponentImplementation` | `name`, `type`, and an `implementation` JSON blob validated against `perfect/app/schema/implementation_schema.json` |
| Part property / a set of parts composed into a configuration (a variant in a variability model) | `Design` | `components` (the selected `Component` rows) and `implementation`, the merged list of component implementations |
| The operating context: world, start pose, goal, anything the stack reads from outside the robot | `Environment` (and `EnvironmentTemplate` for the parameterized form) | `specification` JSON, in the same envvars / launchargs / files vocabulary |
| A parametric constraint evaluation — one (design, environment) pair to be measured | `Experiment` | `design_id`, `environment_id`, `tag` |
| One execution of that pair | `Trial` | `state`, `start_age`, `sim_time`, `uri`, plus the `Update` rows streamed back while it runs |

`Component` is optional. An example may create `ComponentImplementation` rows directly
from a `components.json` (this is what `dummy`, `ros2-turtlebot3` and `SEILR1` do), in
which case a design is built with `designs create ... -i` and keeps no link back to
`Component`. The warning at the top of `_create_design` in
`perfect/app/routes/designs.py` says the same thing.

### What an implementation JSON may contain

`perfect/app/schema/implementation_schema.json` requires at least one of `envvars`,
`launchargs`, `files`:

```json
{
  "envvars":    [{"envvar": "HUSKY_LASER_3D_ENABLED", "value": "true"}],
  "launchargs": [{"arg": "base_global_planner", "value": "navfn/NavfnROS"}],
  "files":      [{"file": "nav2_params.yaml",
                  "updates": [{"keys": "bt_navigator.ros__parameters.default_nav_to_pose_bt_xml",
                               "value": "navigate_to_pose_w_replanning_and_recovery.xml"}]}],
  "parameters": [{"name": "i", "default": 0}]
}
```

- `envvars` become environment variables of the launched ROS process
  (`perfect/experiment/ros/ros.py`).
- `launchargs` become `arg:=value` on the launch command line (same file).
- `files` are edits applied to a working copy of a file the experiment class declares in
  its `_files` mapping; `.yaml` targets are edited key-path by key-path and `.usd` targets
  by prim and attribute (`edit_local_yaml` / `edit_local_usd` in
  `perfect/experiment/experiment.py`).
- `parameters` is not in the schema but is read by
  `perfect/app/routes/designs.py`: each entry's `default` is substituted for `$name`
  everywhere in the implementation when a design is built, which is how one library entry
  serves several instances (`$i` is always the index within its group). It is optional —
  `designs.py` reads it with `.get("parameters", [])`.

This is the "ROS 2 nodes, topics and parameters" side of the binding. PERFECT reaches a
node's parameters through the launch arguments and the parameter YAML the stack already
uses, not by naming nodes directly; the node names live in the launch files under
`perfect/examples/*/launch/` and in the stack's own packages.

## The live binding

The SysML side that exists here is `sysml/models/AGR_stack-MB-SensorTrade-mk6.mdzip`, a
Magic Systems of Systems Architect model. Its constraint blocks hold opaque expressions
that call two MATLAB functions by name and arity:

- `roslaunchtrade(envkey, lpkey, gpkey)` — three integer keys chosen by the solver, mapped
  inside the function to an environment name, a local planner name and a global planner
  name.
- `MatSensorTrade(Amod, Arate, Ahfov, Avfov, Ah, Av, Bh, Bv, Bhfov, Brate, Bmax, Cmax, Crate, Dmod, Drate)`
  — the sensor suite: a depth camera (A), a camera (B), a 2D laser (C) and a 3D laser (D).

Magic Model Analyst evaluates the constraint, MATLAB runs the function, the function POSTs
JSON to `$PERFECT_SERVER_URL/api/v1/run`, and PERFECT creates and enqueues the experiment.
The function returns the experiment id, which is the handle the model keeps for reading
results back. The functions are in `sysml/workbench/bridge/`; that directory's README
records their history and what was substituted in them.

This is "JSON over HTTP", not "JSON over WebSocket". The WebSocket leg is the one inside
PERFECT: `perfect/app/tasks.py` (in the RQ worker) speaks JSON over a WebSocket to the
Runner at `ws://localhost:$RUNNER_PORT` (`perfect/experiment/runner.py`), which launches
the experiment and streams `{"update": ..., "data": ...}` messages back as the trial runs.
Those land in the `Trial` row and in `Update` rows. A SysML tool reads them back with
`GET /api/v1/trials/<id>`, which returns the trial's state and its updates and does not
delete anything. Do not poll `GET /experiments/updates` for this: that is what the HTML
pages use, and it deletes the rows it returns.

### `POST /api/v1/run`

The compatibility endpoint for the bridge functions. It takes the payload those functions
have always sent.

Request, the `roslaunchtrade.m` shape:

```json
{
  "launch_file": "~/auto_stack_ws/src/hardware_launch/launch/navigation_rosbridge.launch",
  "launch_args": {
    "base_global_planner": "navfn/NavfnROS",
    "base_local_planner": "teb_local_planner/TebLocalPlannerROS",
    "domain": "playpen"
  }
}
```

Request, the `MatSensorTrade.m` shape:

```json
{
  "launch_file": "~/auto_stack_ws/src/hardware_launch/launch/navigation_rosbridge.launch",
  "sensor_update": {
    "laser_3d": {"model": "vlp16", "update_rate": 15},
    "camera": {"width": 720, "height": 540, "update_rate": 30, "h_fov": 1.047, "max_range": 50.0},
    "laser_2d": {"update_rate": 25, "max_range": 20.0},
    "depth_camera": {"model": "d435", "width": 1280, "height": 720, "update_rate": 30, "h_fov": 1.5184, "v_fov": 1.0122}
  }
}
```

Both keys may be sent together. What the server does with them:

1. **Picks the library table.** If the `Component` table has rows, components are matched
   there and the design is built from `Component` rows. If it is empty, the match runs
   against `ComponentImplementation` and the design is built with `implementations=True`.
2. **Matches `launch_args`.** `base_global_planner` and `base_local_planner` are looked up
   as component *names*: exact match first, then substring. In the SEILR1 library those
   names are literally `navfn/NavfnROS`, `teb_local_planner/TebLocalPlannerROS` and so on.
   `domain` is not a component; it selects the environment.
3. **Matches `sensor_update`.** Each key is a component *type* (`laser_3d`, `laser_2d`,
   `camera`, `depth_camera`, and any other key is treated as a type too). Candidates are
   the rows of that type; if the value dict has a `model` (or `name`), candidates are
   narrowed to rows whose name contains it, case-insensitively; if it has an
   `update_rate`, candidates are narrowed again to rows whose name contains that number.
   The first surviving candidate wins. This is name matching, and it is a heuristic: the
   reply's `matched` list is there so the caller can see what it actually got.
4. **Finds or creates the design.** The design's name is the matched component names,
   truncated, plus a six-character digest of the request. The same request therefore
   always resolves to the same design instead of creating a new one each call.
5. **Finds or creates the environment.** `launch_args.domain` is matched against
   `Environment.name`, exact then substring. With no `domain`, the lowest-numbered
   environment is used. If neither finds anything, an environment named after the domain
   (or `default`) is created with an empty specification.
6. **Creates the experiment and enqueues one trial**, the same path the CLI's
   `experiments create` plus `experiments run` takes.

`launch_file` is carried into the design implementation as one extra entry
`{"launch_file": "..."}`. No experiment class reads it today — every consumer of a design
implementation reads only `envvars`, `launchargs` and `files`, so the entry is inert — but
it means the path the caller chose is recorded with the design rather than dropped.

Reply (HTTP 201):

```json
{
  "experiment_id": 2,
  "trial_ids": [2],
  "status_url": "http://127.0.0.1:5001/api/v1/experiments/2",
  "design": {"id": 2, "name": "no components #db1a87", "created": true},
  "environment": {"id": 1, "name": "Nothing", "created": false},
  "matched": [
    {"from": "laser_3d", "value": "vlp16", "matched": null},
    {"from": "laser_2d", "value": null, "matched": null},
    {"from": "camera", "value": null, "matched": null},
    {"from": "depth_camera", "value": "d435", "matched": null}
  ],
  "library": "ComponentImplementation"
}
```

That reply is copied from a real run against the `dummy` example, whose library holds only
types `widget` and `ppa`. Nothing matched, so the design has no components — which is the
honest outcome, and why `matched` is in the reply. Against the SEILR1 library the same
request matches the Velodyne Puck (15 Hz) and the Intel RealSense D435.

Then poll `GET /api/v1/experiments/2` for `last_trial_state`. A finished trial reads
`TrialState.SUCCESSFUL|SHUT_DOWN`; `TrialState` is a `Flag`
(`perfect/experiment/experiment.py`), so a terminal state is a combination of flags, not a
single word.

### The rest of the API

| method | route | what it does |
|---|---|---|
| GET | `/api/v1/components` | `Component` rows, each with its `ComponentImplementation` nested when it has one |
| GET | `/api/v1/component_implementations` | `ComponentImplementation` rows (the only library content in examples that create them directly) |
| GET | `/api/v1/designs`, `/api/v1/designs/<id>` | designs with their component list and merged implementation |
| GET | `/api/v1/environments`, `/api/v1/environments/<id>` | environments with the specification parsed to JSON |
| GET | `/api/v1/experiments` | one line per experiment, with `last_trial_id` and `last_trial_state` |
| GET | `/api/v1/experiments/<id>` | the experiment with its design, environment and every trial |
| GET | `/api/v1/environment_templates` | environment templates with their specification, the `$name` placeholders included |
| GET | `/api/v1/trials/<id>` | one trial with its `Update` rows (`?updates=N` to cap, default 100); non-destructive |
| POST | `/api/v1/component_implementations` | create implementations from `{"components": [{"name": ..., "type": ..., "implementation": {...}}, ...]}` (a bare list works too); each is validated against `schema/implementation_schema.json`, and the reply splits them into `created`, `existing` and `invalid` |
| POST | `/api/v1/designs` | create a design from `{"name": ..., "component_implementation_names": [...]}` or the same with `component_implementation_ids`; a design of that name already there comes back with `"created": false` |
| POST | `/api/v1/environment_templates` | create a template from `{"name": ..., "specification": {...}}`, the same shape the CLI loads from a template file |
| POST | `/api/v1/environments` | create an environment from `{"name": ..., "template_id": N, "arguments": {...}}` — the same `$name` substitution the HTML form and the CLI do — or from a `specification` directly |
| POST | `/api/v1/experiments` | create and enqueue from `{"design_ids": [...], "environment_ids": [...], "tag": "..."}`; `design_tag`/`environment_tag` select by tag instead, as the CLI does; `"run": false` creates without enqueuing |
| POST | `/api/v1/experiments/<id>/run` | enqueue another trial of an existing experiment |
| POST | `/api/v1/run` | the bridge endpoint above |

The four library and environment POST routes match on the row's name before they create
anything and return what is already there, so a script that sets a whole project up over
HTTP can be re-run without duplicating it. They call the same create functions the Flask
CLI calls, so a project built this way is identical to one built from `load.bash`. With
them the model-based side never has to touch the CLI: the bridge can create the library,
the design, the environment template, the environment and the experiment in five requests.

**There is no authentication on any of these routes.** Anything that can reach the Flask
port can create designs, environments and experiments and start trials. Bind the server to
localhost, or put it behind something that authenticates, before exposing it.

## The SysML v2 profile

`perfect/sysml-profile/perfect.sysml` is a SysML v2 textual library package that declares
the metadata definitions this binding implies: `ROS2Node`, `ROS2Topic`, `ROS2Parameter`
and `ComponentImplementation`, with attributes mirroring the JSON schema, plus one worked
example binding a `LiDAR` part to a `velodyne_driver` node.

**PERFECT does not parse it.** It is the API-first counterpart to the SysML v1 path that
actually runs here: the mk6 model in Magic Systems of Systems Architect, driven through
Magic Model Analyst and the MATLAB bridge. The profile is written down so that the same
binding can be expressed in a v2 model, and so that the vocabulary is fixed before anyone
writes the reader.
