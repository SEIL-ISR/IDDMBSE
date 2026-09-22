# sensor-suite-sim

A PERFECT example with no simulator behind it: the experiment is a planar
navigation simulation in plain Python, and what it measures depends on which
sensors the design carries and on how cluttered and how dark the environment is.
It is the example the data-driven stage of TRADES-X runs its campaigns against
(`trades-x/case-studies/sensor-suite/run_ddo_campaign.py`).

The point of it is the wiring: a design is a set of sensors drawn from the same
catalogue the model-based stage prices, an environment is a scenario drawn from
a template, and the numbers a trial produces come back through PERFECT's own
trial table, so a design-space exploration tool can submit a campaign and read
the results without knowing anything about the simulation.

## What the robot does

A ground robot crosses a 30 m square field of rocks from one corner to the
other. It plans on an occupancy grid that holds only the rocks its sensors have
reported, descends the cost-to-go field towards the goal one cell per control
step, and re-plans every sixth step, as a real global planner running at a fixed
rate would. A rock the map did not hold when the last plan was made is a rock
the robot can drive into.

A trial runs a batch of independent noise draws over the same rock field and
reports the averages. The grid wavefront and the closed-loop shape are taken
from `case-studies/B2-conformal-perception/cpnav/planner.py` in this repository;
the sensing model, the numbers and the metrics are this example's own. Every
array operation runs over the whole batch at once: the only interpreter loops
are over control steps, over relaxation sweeps and over the eight neighbour
offsets.

## What a sensor is

`catalogue.py` holds the thirteen sensors: four 3-D lidar configurations, four
2-D laser scanners, three depth cameras and two RGB cameras. Each carries its
update rate, horizontal field of view, horizontal angular resolution, maximum
range, price, electrical power, the RAM a five-second buffer of its stream
takes, and whether ambient light matters to it. The price, power and RAM are the
same numbers `trades-x/tradesx/sensitivity.py` prices a design with, so a suite's
totals here and the model-based stage's totals are the same value;
`tests/test_catalogue.py` checks that against seven reference designs.

A sensor reports a rock of radius `r` at distance `d` with probability
`exp(-d / L)` where `L = 2 r / (SAMPLES_TO_RESOLVE * ares)`, inside its field of
view and inside its maximum range. `L` is the distance at which the rock stops
covering enough of the sensor's angular samples. One control step is longer than
one sensor frame, so a sensor gets several looks; repeated looks at a static
rock are correlated, so the effective number of independent looks grows as the
square root of the frames per step. For the depth and RGB cameras the scenario's
visibility scales both the maximum range and the probability; the lidar and
laser scanners carry their own illumination and do not notice it.

That is what makes the suites differ. A depth camera sees everything within six
metres and nothing beyond it, and in the dark its six metres shrink. An RGB
camera has the finest angular resolution in the catalogue and the narrowest
field of view. A lidar sees all around itself, in any light, but resolves a rock
later than a camera does.

## How the design and the environment reach the simulation

Through PERFECT's own file-editing mechanism, not through a side channel.

`components.json` gives every sensor one component implementation whose
`implementation` is a single `files` update appending the sensor's entry to
`suite` in `sensors.yaml`. PERFECT copies `sensors.yaml` into the trial's
working directory and applies the update of every component in the design, so
after the copy the file holds exactly the suite under test.

`environment_template.json` is an environment template with four arguments —
`$clutter`, `$visibility`, `$seed`, `$n_draws` — that write themselves into
`scenario.yaml` the same way. An environment created from it with concrete
values carries those values into the trial.

`experiment.py` reads those two files, hands their contents to `sensor_sim.py`,
and relays the metrics back with `await self._relay_update("metrics", ...)`,
which PERFECT stores as an `Update` row on the trial and
`GET /api/v1/trials/<id>` returns. `sim_time` is relayed separately because
`Trial` has a column of that name.

## What a trial reports

`success_rate`, `collision_rate`, `stall_rate`, `time_to_goal`, `path_length`,
`tortuosity` (path length over the straight-line distance), `detection_rate`,
`detection_distance` (the mean range at which a rock was first reported),
`battery_soc` (the state of charge left after the run, from the suite's power
draw and the time it took), `sim_time`, `replans`, `n_rocks`, `n_sensors`, the
suite's `cost`, `power` and `ram`, and the three scenario parameters.

A draw that collides or runs out of steps is charged the whole mission budget
for its time and its path length, so failing is never cheaper than arriving and
the table stays finite when no draw arrives.

## The interpreter

The simulation is numpy. The Python environment that carries PERFECT does not
have to be: `experiment.py` starts `sensor_sim.py` in a child process, with the
interpreter named by `SENSOR_SIM_PYTHON` if that is set and the running one
otherwise. Point it at any Python 3 with numpy.

## Run one trial without a server

```bash
cd perfect/examples/sensor-suite-sim
PERFECT_PROJECT_ROOT=$PWD SENSOR_SIM_PYTHON=$(which python3) python experiment.py
```

That builds a four-sensor design and one scenario off the template in process
and runs the full experiment lifecycle with the mock callbacks, printing every
state change and the metrics. Recorded on 2026-09-22 with the VLP-16-A,
LMS111-b1, D435, Blackfly-A suite at clutter 0.5, visibility 0.4, seed 1, 12
draws:

```
INFO core experiment._init:72 - 4 sensors, scenario {'clutter': 0.5, 'n_draws': 12.0, 'seed': 1.0, 'visibility': 0.4}
INFO core experiment._run:94 - success_rate 1.0 time_to_goal 37.48 detection_distance 13.91
INFO core experiment.mock_relay_update_callback:357 - Experiment 0 update metrics to {... 'success_rate': 1.0, 'collision_rate': 0.0, 'time_to_goal': 37.47809639811225, 'tortuosity': 1.0392555336889526, 'detection_distance': 13.906843078296447, 'battery_soc': 0.9244191060525035, 'cost': 15500.0, 'power': 121.000106, 'ram': 7698.15 ...}
INFO core experiment.run:293 - Shut down SensorSuiteExperiment
```

The simulation itself also runs on its own:

```bash
echo '{"suite": [], "scenario": {"clutter": 0.6, "visibility": 1.0, "seed": 2, "n_draws": 4}}' > job.json
python3 sensor_sim.py job.json metrics.json
# success_rate 0.0 time_to_goal 120.0 detection_distance 0.0
```

An empty suite is a legal design, and a robot with no sensors hits a rock.

## Run it under a PERFECT stack

The bring-up is the one `perfect/README.md` records for the `dummy` example,
with this directory as `PERFECT_PROJECT_ROOT` and `SENSOR_SIM_PYTHON` exported
to every process that needs it. After `db upgrade`:

```bash
python -m flask --app perfect.app components load_component_implementations components.json
python -m flask --app perfect.app environments create_templates_from_file environment_template.json
python -m flask --app perfect.app designs create "VLP-16-A" "LMS111-b1" "D435" "Blackfly-A" \
    -i --name "design-4234" --tag ddo
python -m flask --app perfect.app environments create_from_template 1 \
    clutter:=0.5 visibility:=0.4 seed:=1 n_draws:=12 -n "c0.5-v0.4-s1" -t ddo
python -m flask --app perfect.app experiments create ddo ddo -t ddo
python -m flask --app perfect.app experiments run ddo
```

The same sequence over HTTP is what `tradesx.ddo_api` does, and
`trades-x/case-studies/sensor-suite/README.md` records a 180-trial campaign run
that way.

## Tests

The tests need numpy and pytest:

```bash
cd perfect/examples/sensor-suite-sim
python3 -m pytest tests -q
```

They check the batched cost-to-go against a Dijkstra oracle with a priority
queue, the batched detection probability against a triple Python loop over
draws, rocks and sensors, the occupancy rasterisation against a cell-by-cell
loop, that darkness costs a depth camera its range and costs a lidar nothing,
that the same trial twice gives the same numbers, and that the catalogue's
totals are the model-based oracles' numbers. Recorded on 2026-09-22:

```
..............................                                           [100%]
30 passed in 0.71s
```

## Files

| file | what it is |
|---|---|
| `experiment.py` | the PERFECT experiment class; reads the two working files, runs the simulation, relays the metrics |
| `sensor_sim.py` | the simulation: rock field, sensing, grid wavefront, closed loop, metrics |
| `catalogue.py` | the thirteen sensors; running it rewrites `components.json` |
| `components.json` | the sensor library, one component implementation per sensor |
| `sensors.yaml` | the suite, empty by default; the design fills it |
| `scenario.yaml` | the scenario defaults; the environment overwrites them |
| `environment_template.json` | the environment template with `$clutter`, `$visibility`, `$seed`, `$n_draws` |
| `tests/` | the batched pieces against brute-force oracles, and the catalogue against the model-based ones |
