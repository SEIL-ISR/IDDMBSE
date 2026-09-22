# Case study: the test range as the design under trade

The contested-terrain range in `isaacsim/` has five knobs that
`isaacsim/tools/range_doe.py` turns into a USD layer: obstacle coverage, a
99th-percentile slope target, a static/dynamic friction pair and a restitution.
A range configuration is a design like any other. It has to be contested
enough to tell robot designs apart and traversable enough that a run produces
data, and those two pull against each other. This study runs both stages of
TRADES-X on it: a model-based stage that scores the whole DOE grid from the
heightmap and the rock statistics, and a data-driven stage that ranks the
eight configurations PERFECT ran in Isaac Sim (`isaacsim/results/campaign.csv`)
by what the trials measured.

```
cd trades-x
uv sync --extra ad
uv run python case-studies/range/run_range_study.py
```

The run takes about 4 s on a CPU and writes `results/` and `figures/`. Two runs
write byte-identical results.

## The model

`tradesx/range_model.py` predicts what a trial will face from the knobs and
the shipped heightmap (`isaacsim/range/terrain/heightmap.npz`), with the same
constants the range and the PERFECT example use:

| attribute | how it is computed |
|---|---|
| rocks per m² | coverage / mean rock footprint; `range_doe.py` draws diameters uniformly in [1, 3] m, so the mean footprint is π/4 · 4 · (1 + 0.5²/3) = 3.40 m² |
| encounters per m | rocks per m² × 3 m (the 1.5 m encounter radius of `sim_trial.py`, both sides) × 0.75 (the 3 m keep-out disc around the start, inside the 6 m start area) |
| chance of an encounter | 1 − exp(−encounters per m × 18 m), over the commanded 0.6 m/s × 30 s |
| mean free path | 1 / (rocks per m² × 0.75 × (mean diameter 2 m + wheel track 0.413 m)) |
| progress fraction | expected distance before the first blocking rock over 18 m, less the slide-back after a rebound, (e · v)² / (2 μ_d g) |
| height scale k | tan(target) / g99, where g99 is the 99th percentile of the unscaled gradient on the 4.8 cm grid: the scaling `range_doe.slope_scale_for` applies |
| grade | atan(k · g) over the 191 wheel-scale cells (16 × 16 blocks, 77 cm) within 6 m of the start at (−18.75, −5.31); mean and 90th percentile |
| no-slip margin | μ_s − tan(90th-percentile grade) |
| slip share | mean((k g − μ_s)₊) / mean(k g): the part of the start area's climbing demand that static friction does not hold |
| relief | each cell's grade as a share of the 0.35 rad (20.05°) attitude bound of `veritas/runtime/stl-observer/specs/range_safety.yaml`, capped at 1, averaged |
| attitude share | 1 at or below the bound, falling linearly to 0 at twice the bound, averaged |

**Contestedness** is the mean of the chance of an encounter, the relief and the
slip share. **Predicted traversability** is progress fraction × (1 − slip
share) × attitude share. The height scales the model computes for the 15° and
25° targets, 0.213048 and 0.370764, are the ones the PERFECT trials recorded.

## The requirement partition

`requirements.yaml` splits what a range configuration has to satisfy before
anything runs. The three model-based requirements prune the DOE grid; the five
data-driven ones are checked on the trial table. The thresholds are the range's
own: the 5 m progress floor, the 0.35 rad attitude bound of the VERITAS
observer spec, and the stuck and unstable flags as `sim_trial.py` sets them.

| id | class | requirement | bound |
|---|---|---|---|
| RR.1 | model-based | 90th-percentile start-area grade | ≤ 20.05° |
| RR.2 | model-based | obstacle coverage | 0.1 to 0.6 |
| RR.3 | model-based | no-slip margin | ≥ 0 |
| RR.4 | data-driven | distance in 30 s | ≥ 5 m |
| RR.5 | data-driven | maximum roll | ≤ 20.05° |
| RR.6 | data-driven | maximum pitch | ≤ 20.05° |
| RR.7 | data-driven | stuck (below 0.05 m/s for more than 2 s) | no |
| RR.8 | data-driven | unstable (above 10 m/s) | no |

## Model-based stage

The DOE grid is coverage 0.05 to 0.9 in steps of 0.05, slope targets 5° to 35°
in steps of 2.5°, eight friction pairs 0.3/0.2 to 1.0/0.9 and restitution 0.0,
0.1 and 0.3: 18 × 13 × 8 × 3 = 5616 configurations, scored in one numpy
broadcast. The run printed

```
DOE grid: 5616 configurations; RR.1 passes 3456, RR.2 passes 3432, RR.3 passes 4968
feasible: 2079  frontier: 68 configurations, 32 distinct score pairs
```

The Pareto filter (`tradesx.pareto.non_dominated`, contestedness and
predicted traversability both maximised) over the 2079 feasible configurations
keeps 68. They run from contestedness 0.299 at traversability 0.644 (coverage
0.1, slope 12.5°) to 0.466 at 0.162 (coverage 0.6, slope 22.5°, friction
0.4/0.3). Configurations that differ only in a friction the start area never
needs score the same, which is why 68 configurations give 32 score pairs.
Every frontier point has restitution 0.0: at 0.6 m/s a rebound slides the AGR
back a few millimetres, so restitution only ever costs traversability in the
model. The slope targets on the frontier are 12.5° to 22.5°; 25° puts the
start area's 90th-percentile grade at 20.16°, just past RR.1. A few frontier
rows, from `results/mbo_frontier.csv`:

| coverage | slope | friction | contestedness | traversability | encounter chance | mean free path m | p90 grade | no-slip margin | slip share |
|---|---|---|---|---|---|---|---|---|---|
| 0.1 | 12.5° | 0.4/0.3 | 0.2994 | 0.6436 | 0.696 | 18.81 | 9.90° | 0.226 | 0.0 |
| 0.1 | 15.0° | 0.6/0.5 | 0.3126 | 0.6426 | 0.696 | 18.81 | 11.91° | 0.389 | 0.0 |
| 0.1 | 22.5° | 0.4/0.3 | 0.3652 | 0.5998 | 0.696 | 18.81 | 18.06° | 0.074 | 0.0491 |
| 0.15 | 22.5° | 0.4/0.3 | 0.4107 | 0.4947 | 0.832 | 12.54 | 18.06° | 0.074 | 0.0491 |
| 0.6 | 22.5° | 0.4/0.3 | 0.4664 | 0.1618 | 0.999 | 3.13 | 18.06° | 0.074 | 0.0491 |

`results/mbo_grid.csv` has all 5616 rows with every attribute, the three
requirement flags, feasibility and frontier membership.

## Data-driven stage

The eight trials of `isaacsim/results/campaign.csv` are the campaign: one Carter
v2.4 over coverage 0.1, 0.4 and 0.8 crossed with slope targets 15° and 25°,
coverage 0.3 at 15°, and coverage 0.1 at the terrain's authored relief, all at
friction 0.6/0.5 and restitution 0.1. `authored` is a category, not a slope
target: `range_doe.py` writes no height scale for it, so the model evaluates it
at k = 1, and its knob row carries the 99th-percentile slope the trial
measured, 51.51°.

Requirements met per trial (1 = met), as printed:

| trial | configuration | RR.1 | RR.2 | RR.3 | RR.4 | RR.5 | RR.6 | RR.7 | RR.8 |
|---|---|---|---|---|---|---|---|---|---|
| 1 | d0.1 s15.0 | 1 | 1 | 1 | 1 | 1 | 1 | 1 | 1 |
| 2 | d0.1 s25.0 | 0 | 1 | 1 | 1 | 1 | 1 | 1 | 1 |
| 3 | d0.4 s15.0 | 1 | 1 | 1 | 1 | 1 | 1 | 1 | 1 |
| 4 | d0.4 s25.0 | 0 | 1 | 1 | 1 | 1 | 1 | 1 | 1 |
| 5 | d0.8 s15.0 | 1 | 0 | 1 | 0 | 1 | 1 | 0 | 1 |
| 6 | d0.8 s25.0 | 0 | 0 | 1 | 1 | 1 | 1 | 1 | 1 |
| 7 | d0.3 s15.0 | 1 | 1 | 1 | 1 | 0 | 1 | 1 | 1 |
| 8 | d0.1 authored | 0 | 1 | 0 | 0 | 0 | 1 | 1 | 1 |

The MAVF (`tradesx.ddo_api.rank_designs`, the weighting the sensor-suite study
uses) runs over the model's two scores and six measured attributes: distance,
obstacle encounters and mean pitch maximised, maximum roll, stuck and unstable
minimised. Three of the eight requirements are model-based and five
data-driven, so the model's scores carry 3/8 of the weight and the measured
attributes 5/8. The ranking, from `results/mavf_ranking.csv`:

| rank | configuration | MAVF | model-only rank | contestedness | traversability | distance m | encounters | mean pitch | max roll |
|---|---|---|---|---|---|---|---|---|---|
| 1 | d0.1 s25.0 | 0.6985 | 2 | 0.363 | 0.617 | 9.72 | 0 | 10.8° | 15.8° |
| 2 | d0.4 s15.0 | 0.6737 | 6 | 0.411 | 0.255 | 13.45 | 3 | 6.4° | 14.5° |
| 3 | d0.3 s15.0 | 0.6631 | 5 | 0.405 | 0.328 | 13.20 | 2 | 7.3° | 29.7° |
| 4 | d0.4 s25.0 | 0.6479 | 4 | 0.462 | 0.245 | 9.72 | 0 | 10.8° | 15.8° |
| 5 | d0.1 s15.0 | 0.6178 | 3 | 0.313 | 0.643 | 12.99 | 0 | 6.3° | 14.5° |
| 6 | d0.8 s25.0 | 0.5348 | 7 | 0.465 | 0.125 | 5.54 | 0 | 8.9° | 8.8° |
| 7 | d0.1 authored | 0.4926 | 1 | 0.532 | 0.378 | 3.71 | 0 | 5.0° | 179.0° |
| 8 | d0.8 s15.0 | 0.2971 | 8 | 0.414 | 0.130 | 3.21 | 0 | 5.0° | 6.3° |

On the model's scores alone the authored relief ranks first: it is the most
contested configuration in the table, and its predicted traversability, 0.378,
is above that of the coverage 0.3 and 0.4 configurations at 15°. In the trial the AGR rolled to 179° after 3.7 m, and it drops to
seventh. The two coverage-0.4 and 0.3 configurations at 15° rise from sixth and
fifth to second and third: the blocking model counts a rock in the path as the
end of progress, while in the trials the AGR was pushed round the rocks and
kept going, covering 13.4 m at coverage 0.4 where the model expects 4.6 m
before the first block. Coverage 0.8 at 15° is last on both, the one trial that
got stuck.

`results/ddo_metrics.csv` is the configuration-by-metric table with every
requirement flag and the model's two scores beside the measurements.

## Sensitivity

`tradesx/range_model.py` is written against a numerical module, so the same
formulas run under `jax.numpy`. `relative_sensitivities` takes x · d(score)/dx
for the five knobs at every frontier point by JAX forward mode, and
`relative_sensitivities_fd` does it again by central differences; the run
printed a largest gap of 9.2e-11 between the two. The requirement side moves
each model-based threshold by 10 % either way (±0.1 on RR.3's zero bound),
recomputes the frontier and reports the share that changes: configurations on
one frontier and not the other, over those on either. From `results/sensitivity.csv`:

| knob | requirement | mean \|x dC/dx\| | mean \|x dT/dx\| |
|---|---|---|---|
| obstacle coverage | RR.2 | 0.0968 | 0.2639 |
| slope target | RR.1 | 0.1057 | 0.0414 |
| static friction | RR.3 | 0.0116 | 0.0138 |
| dynamic friction | | 0.0 | 0.0 |
| restitution | | 0.0 | 0.0 |

| threshold moved | share of the frontier that changes, down | up |
|---|---|---|
| RR.1 grade ≤ 20.05° | 0.542 | 0.571 |
| RR.2 lower end 0.1 | 0.0 | 0.573 |
| RR.2 upper end 0.6 | 0.029 | 0.014 |
| RR.3 margin ≥ 0 | 0.481 | 0.418 |

Coverage moves traversability most and the slope target moves contestedness
most. The frontier leans hardest on the grade bound and on the lower end of the
coverage band: 33 of the 68 frontier configurations sit at coverage 0.1, so
raising that end to 0.11 changes 57 % of the frontier. Dynamic
friction and restitution enter only through the rebound slide-back, which is
zero at the frontier's restitution of 0.0.

## The next campaign

67 of the 68 frontier configurations are new to the campaign table; the one
already measured is
coverage 0.1, slope 15°, friction 0.6/0.5 (trial 1, whose restitution of 0.1
the match leaves out). One configuration per distinct score pair, the lowest
static friction of each tie, gives 32; eight of those, evenly spaced along the
frontier, are the next campaign, in `results/next_campaign_points.json`.
`results/next_campaign.txt` holds the command, run from the repository root
against a PERFECT stack brought up on the `isaacsim-range` example:

```
cd isaacsim/tools
python range_campaign.py --submit --project-root ../../perfect/examples/isaacsim-range \
    --densities 0.1 --slopes 12.5 --frictions 0.4/0.3 --restitutions 0.0 --seeds 7 --duration 30 \
    --robots "Carter v2.4" --tag range-next \
    --extra ../../trades-x/case-studies/range/results/next_campaign_points.json
```

`range_campaign.py --plan` with the same arguments lists the eight points:

```
8 grid points x 1 robots = 8 trials
  density 0.1, slope 12.5, friction 0.4/0.3, seed 7
  density 0.1, slope 17.5, friction 0.5/0.4, seed 7
  density 0.1, slope 22.5, friction 0.5/0.4, seed 7
  density 0.15, slope 20.0, friction 0.6/0.5, seed 7
  density 0.15, slope 22.5, friction 0.4/0.3, seed 7
  density 0.2, slope 22.5, friction 0.4/0.3, seed 7
  density 0.4, slope 22.5, friction 0.4/0.3, seed 7
  density 0.6, slope 22.5, friction 0.4/0.3, seed 7
```

They move the friction knob, which the recorded campaign held at 0.6/0.5, and
cover slope targets from 12.5° to 22.5°, where the frontier lies.

## Figures

All three are SVG and PDF in `figures/`.

- `mbo_grid_frontier`: left, the coverage × slope grid at the recorded
  friction and restitution coloured by contestedness, with the configurations
  that fail a model-based requirement crossed, the frontier configurations
  circled and the measured ones starred; right, all 5616 configurations in
  contestedness × predicted traversability, the frontier, the next campaign's
  eight points and the eight measured configurations numbered by trial.
- `mavf_ranking`: the eight measured configurations, the MAVF on the model's
  scores alone beside the MAVF with the measured attributes, in the order of
  the second.
- `sensitivity`: left, the knob sensitivities of both scores over the frontier;
  right, the share of the frontier that changes when each model-based
  threshold moves.

## Tests

`tests/test_range_study.py`: the attributes against a brute-force oracle that
walks one configuration and one cell at a time, the gradient of a tilted plane
at three windows, the height scales against the recorded campaign, JAX against
central differences, the frontier and the MAVF ranking on hand-built cases, the
requirement partition, and a full run into a temporary directory that must
reproduce the shipped result files byte for byte.
