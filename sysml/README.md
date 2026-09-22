# SysML model and MATLAB workbench (AGR_stack)

The SysML v1 side of IDDMBSE: the descriptive model of the Autonomous Ground Robot
stack, the trade-study pattern built on top of it, and the MATLAB functions that the
model calls to launch experiments on a PERFECT server.

The model was built in Magic Systems of Systems Architect (Magic SoSA) 2022x between
November 2023 and February 2024 and is shipped here as one `.mdzip` file. It is the
model behind the SysML parts of the IDDMBSE paper (`manuscript/`), which describes
PERFECT as driving Magic SoSA through the Magic Model Analyst engine and a
SysML-to-MATLAB bridge.

## What is here

```
models/     the canonical model file and its version history
workbench/  the MATLAB functions the model calls, the design-space scripts, and their results
ros1-husky-config/  the ROS 1 launch and parameter files the experiments ran against
```

## Opening the model

`models/AGR_stack-MB-SensorTrade-mk6.mdzip` needs **Magic Systems of Systems Architect
2022x or later** (the file records `MagicDraw UML 2022x` as its extender). The model
will not open usefully without these plugins:

- SysML
- Cameo Requirements Modeler (requirement tables and the requirement customization)
- Magic Model Analyst / Cameo Simulation Toolkit (the simulation configurations and the
  parametric execution that drives the MATLAB calls)
- Dependency Matrix and DSL Customization (the instance tables)
- Validation
- Parametric Execution

It mounts nine library projects, which the tool resolves from its own installation:

`UML_Standard_Profile`, `MD_customization_for_SysML`, `SysML Profile`,
`MD Customization for Requirements`, `Free_Form_Elements_Profile`,
`ParametricExecutionProfile`, `SimulationProfile`, `ISO-80000`, `ISO-80000-Extension`.

The mount URIs recorded in the file point at `file:/G:/Magic SoSA/profiles/...` and
`file:/G:/Magic SoSA/modelLibraries/...` (and, for three of them, an older
`file:/C:/Program Files/MD_UML_.../profiles/...`), i.e. at the drive where the modeller's
Magic SoSA was installed. These are standard libraries that ship with the tool, so a
reader's own install should supply them from its own paths — **[unverified]**: nobody has
opened this file on a fresh install here, and no Magic SoSA is available on this
workstation. If the tool does not re-resolve them automatically, they are re-pointed
through Options > Environment > Path Variables / the "Locate" dialog on load.

## Lineage

The lab's drop contained seven snapshots of one lineage and six autosave `.bak` files.
The snapshots run `Iddmbse_v2.mdzip` (2023-11-30) through `Iddmbse_v2_perfect-mk1` ...
`-mk5-SensorTrade` to `MB-SensorTrade-Iddmbse_perfect-mk6.mdzip` (2024-02-14); the model
only ever grows (4658 to 8875 XML elements, measured here) and packages are only added,
so **mk6 is the only snapshot shipped**. The others are kept outside the repository;
`models/LINEAGE.md` has the table, the measurements and the path.

## Package map (mk6)

Model root: `AGR_stack`.

| package | contents |
|---|---|
| Unit Imports | ISO-80000 basic unit packages (length, mass, time, ...) |
| AGR Structural Diagrams | Context-Level Structure, System-Level Structure, Blocks (BDDs and IBDs of the stack, sensor suite, power module) |
| AGR Behavioral Diagrams | Context-Level Behavior (use case), System-Level Behavior (perception activity, battery state machine) |
| Model Libraries / Model Instances | the design alternatives: RealSense d415/d435/d455, Velodyne VLP-16 and HDL-32E, SICK LMS111/LMS151 (a and b), FLIR Blackfly (A and B), the environments inspection / agriculture / orchard / playpen, local planners DWA / TEB / Trajectory Rollout, global planners Dijkstra / A* |
| Requirements | 23 SysML requirements (business, functional, performance, stakeholder) with satisfy and derive links |
| Trade Studies | the trade-study blocks and their instance tables |
| PerfECT Analysis | SimConfigsTradeStudy, Results, ROS Launch Trade -- the simulation configurations that run the studies |
| Simulations, Demos | the battery FMU demo and the PerfECT monitor demo |
| RELLIS-utils | Rellis3D Data and Rellis3D Emulated Data placeholders |
| Software Tooling | tool blocks used by the demo diagrams |

Counts measured from mk6: 69 `sysml:Block`, 3 `sysml:ConstraintBlock`, 23
`sysml:Requirement`, 51 diagrams.

## The trade-study pattern

A trade study is one block whose properties are the design variables, plus a constraint
block whose expression is evaluated by Magic Model Analyst:

- `SensorTradeStudyMeta` -- the sensor design space (depth camera model and resolution
  and rate and field of view, camera, 2D laser, 3D lidar model and rate). Its instance
  table enumerates the sensor configurations; `All Sensor Configs Instance Table`
  collects them.
- `ROSLaunchTradeStudyMeta` -- the autonomy-configuration space (global planner, local
  planner, environment). The `roslaunchtradestudymeta at <timestamp>` instances saved in
  the model are the runs executed in December 2023.
- Constraint blocks `MatSensorTrade`, `roslaunchtrade` and `Objective Fcost`. The first
  two carry opaque expressions whose language is `Matlab` and whose bodies are literally
  `mat_out_sen = MatSensorTrade(Amod,Arate,Ahfov,Avfov,Ah,Av,Bh,Bv,Bhfov,Brate,Bmax,Cmax,Crate,Dmod,Drate)`
  and `mat_out = roslaunchtrade(envkey,lpkey,gpkey)`. Those functions live in
  `workbench/bridge/`.

So the chain is: instance table row -> simulation configuration -> parametric execution
evaluates the constraint block -> Magic Model Analyst calls the MATLAB function ->
the function POSTs the configuration to the PERFECT server, which launches the ROS 1
stack in `ros1-husky-config/`. Results came back as rosbags and were scored by the
scripts in `workbench/rosbag/` and `workbench/dse/`.

## References inside the model that will not resolve

These are recorded in the file and are left untouched (the `.mdzip` is shipped
byte-for-byte). They break the battery simulation config and two decorative images, and
nothing else. Paths are written below with forward slashes so a path scan of this
repository does not trip on them:

- `C:/Users/sdamera/Desktop/ee_hv_battery_charge_discharge.fmu` -- the FMU referenced by
  the FMU-stereotyped battery block and by the `sim_config_battery` /
  `ee_hv_battery_charge_discharge` diagrams. The FMU is not in the lab's drop and is not
  shipped here.
- `C:/Users/sdamera/Desktop/SLIDES/Matlab_Logo.png` and
  `C:/Users/sdamera/Desktop/SLIDES/Python.svg.png` -- two images placed on the
  `PerfECT Monitor Demo` / overview diagrams.

## What this is not

- There is no PERFECT, TRADES-X or VERITAS SysML profile. Nothing in this model is a
  reusable stereotype library for the toolchain. The connection to PERFECT is exactly
  the opaque expressions above, calling MATLAB functions that make an HTTP request.
- There is no SysML v2 model here, and no automated round trip: results came back as
  files, not as model updates.
- The model is a 2023-24 artifact tied to the ROS 1 SEIL-R1 Husky stack. The ROS 2 work
  in `seil-r2/` is a separate, later stack.

## Cross-links

- `workbench/README.md` -- how the MATLAB bridge worked, what each script does, and the
  environment variables introduced here in place of the lab's hard-coded address and
  paths.
- `trades-x/` -- the Python port of the Pareto and MAVF scoring that
  `workbench/dse/` and `workbench/rosbag/` do in MATLAB. The CSVs in
  `workbench/results/` are the inputs.
- `perfect/` -- the runner the bridge POSTs to. `perfect/examples/SEILR1/experiment.py`
  is the example for this same Husky stack: it reads a sensor YAML of the shape in
  `ros1-husky-config/sensor.yaml`, turns it into launch arguments, and launches
  `$SEILR1_WS/src/hardware_launch/launch/navigation.launch`.
- `ros1-husky-config/README.md` -- what the launch and parameter files expect.
