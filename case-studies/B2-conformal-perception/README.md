# Case study B2 — Robust perception via conformal prediction

This directory implements Section IV-B.2 of the paper as a self-contained
simulation: a synthetic detector and a synthetic arena, run through a closed
navigation loop with and without conformal prediction. What each simulated
piece is appears below.

## What the paper claims

> Learned perception fails silently: a missed or mislocalized detection
> propagates into an unsafe plan. We harden the perception module with
> conformal prediction (CP), which wraps any detector in a distribution-free
> guarantee. Given a calibration set, CP constructs a prediction region
> R_alpha(x) around a detector output f(x; theta) such that
> P(f(x; theta) in R_alpha(x)) >= 1 - alpha, for a user-chosen miscoverage
> level alpha. We apply this to object detection, inflating each bounding box
> to its (1 - alpha) conformal region before it reaches the planner, so that
> collision avoidance carries an assurance which survives the closed-loop
> distribution shift the planner itself induces.

and, on the tool chain:

> Conformal calibration is only as sound as its calibration data, which must be
> ground-truth-labeled and drawn from the closed-loop states the robot will
> actually visit; PERFECT produces exactly that ... TRADES-X then treats the
> coverage level 1 - alpha as a design variable, trading it against navigation
> conservativeness.

The figure the paper carries shows realized AGR trajectories without and with
conformalized detections. `figures/trajectories.svg` is the analogue built
here.

## What this directory does

A 20 m by 20 m arena with axis-aligned rectangular obstacles is the world. A
point-goal navigation task runs a closed loop: at every control step the
robot detects the obstacles it can see, optionally
inflates each detection to its conformal region, rasterizes the result into an
occupancy grid, recomputes the cost-to-go to the goal, moves one cell, and is
checked for collision against the **true** obstacles. Five steps:

1. **Campaign** (`cpnav/campaign.py`). Run the nominal closed loop over
   randomly drawn worlds and record, for every frame, one row per detection
   with the ground-truth box beside it. The table it writes has the shape a
   PERFECT Trial result carries (flat per-detection rows keyed by episode and
   frame), so a campaign export in that shape drops in unchanged. Written to
   `results/campaign.csv`. **Through PERFECT** below runs the same step as a
   real PERFECT campaign, over three detector configurations and three clutter
   bands, and calibrates on what the trials wrote back.
2. **Calibrate** (`cpnav/conformal.py`). Split conformal prediction on boxes.
   The nonconformity score of a detection `d` against the truth `t` is the
   smallest uniform outward inflation that makes `d` cover `t`:

       s(d, t) = max(d_xmin - t_xmin, d_ymin - t_ymin, t_xmax - d_xmax, t_ymax - d_ymax)

   The conformal quantile is the k-th smallest calibration score with
   `k = ceil((n + 1)(1 - alpha))`, the finite-sample correction that makes the
   marginal guarantee hold; if `k > n` the quantile is `+inf` and the
   calibration set is too small for that level. Inflating a detection by `q`
   covers the truth exactly when its score is at most `q`, which is what makes
   the procedure valid.
3. **Check coverage** on held-out episodes. The split is over whole episodes,
   not over rows: consecutive frames inside one episode see the same objects
   from nearby poses and are not exchangeable with each other. For the same
   reason the interval reported beside the coverage is a bootstrap over
   episodes, not a binomial interval over rows.
4. **Close the loop** (`cpnav/planner.py`). Run K test episodes twice on the
   same worlds, once with the raw detections and once with the conformalized
   ones, and count collisions, successes, stalls and path length.
5. **Trade off** (`cpnav/tradeoff.py`). Sweep alpha, and for each value report
   the coverage bought and the conservativeness it costs. This is the TRADES-X
   hook: 1 - alpha is a design variable, and the sweep is the trade-off table a
   TRADES-X stage would optimize over.

## How to run

    cd case-studies/B2-conformal-perception
    uv sync
    uv run pytest -q
    uv run python run_case_study.py

The script is seeded (`SEED` at the top of `run_case_study.py`) and writes
`figures/trajectories.{svg,pdf}`, `figures/tradeoff.{svg,pdf}`,
`results/campaign.csv`, `results/alpha_sweep.csv` and `results/summary.json`.

`run_perfect_campaign.py` runs the calibration campaign against a live PERFECT
server instead, and writes into `results/perfect/` and the `perfect_*` figures.
**Through PERFECT** below records it.

## Results

One seeded run, `SEED = 20260922`, measured 2026-09-22. `uv run pytest -q` is
30 passed. The script took between 104 s and 121 s over four runs of this
workstation, which was sharing its cores with another job; consecutive runs
write byte-identical `results/` files.

The campaign is 90 episodes with every fourth frame kept, 2039 detection rows.
Sixty episodes (1312 rows) calibrate, thirty (727 rows) are held out.
Nonconformity scores over the calibration rows: median 0.182 m, mean 0.269 m,
max 1.248 m.

Calibration and coverage on the held-out episodes:

| alpha | target 1 - alpha | q (m) | held-out coverage | 90% episode bootstrap |
|---|---|---|---|---|
| 0.30 | 0.70 | 0.244 | 0.6850 | 0.6428 - 0.7303 |
| 0.20 | 0.80 | 0.325 | 0.7882 | 0.7355 - 0.8423 |
| 0.15 | 0.85 | 0.538 | 0.8514 | 0.7975 - 0.9028 |
| 0.10 | 0.90 | 0.680 | 0.9037 | 0.8563 - 0.9429 |
| 0.05 | 0.95 | 0.839 | 0.9422 | 0.9164 - 0.9672 |
| 0.02 | 0.98 | 0.963 | 0.9807 | 0.9690 - 0.9904 |
| 0.01 | 0.99 | 1.034 | 0.9904 | 0.9824 - 0.9963 |

Every target lies inside its bootstrap interval. Four of the seven point
estimates sit above target and three below; with thirty held-out episodes and
strongly correlated rows inside each one, the interval is the number to read,
not the point estimate. At the operating point alpha = 0.10 the held-out
coverage is 0.9037, above the 0.90 target.

Closed loop, 200 test episodes per arm, the same 200 worlds for every arm.
Success, collision and stall partition the 200; the mean path length is over
the successful episodes; a waiting step is one where the inflated detections
left no path and the robot held position.

| arm | q (m) | collisions / 200 | success rate | stalls / 200 | mean path (m) | mean waiting steps |
|---|---|---|---|---|---|---|
| nominal | 0.000 | 168 | 0.160 | 0 | 26.54 | 0.00 |
| alpha = 0.30 | 0.244 | 60 | 0.700 | 0 | 27.64 | 0.02 |
| alpha = 0.20 | 0.325 | 51 | 0.740 | 1 | 27.89 | 0.02 |
| alpha = 0.15 | 0.538 | 32 | 0.840 | 0 | 29.05 | 0.01 |
| alpha = 0.10 | 0.680 | 16 | 0.915 | 1 | 29.76 | 0.03 |
| alpha = 0.05 | 0.839 | 1 | 0.965 | 6 | 30.36 | 0.38 |
| alpha = 0.02 | 0.963 | 1 | 0.945 | 10 | 30.66 | 1.01 |
| alpha = 0.01 | 1.034 | 2 | 0.915 | 15 | 30.73 | 1.39 |

At the operating point alpha = 0.10 the collisions fall from 168 to 16 of 200
episodes and the mean path length rises from 26.54 m to 29.76 m, 12 percent
longer. The realized coverage inside that arm's own closed loop is 0.9482,
against 0.9037 on the held-out nominal episodes.

The trade-off the sweep exposes is the TRADES-X one. Collisions keep falling
to alpha = 0.05, where the margin starts closing corridors instead of clearing
obstacles: stalls climb from 1 to 15 and the success rate peaks at alpha = 0.05
and then falls, because the robot spends its step budget waiting. On these
worlds the operating point that buys the most safety without stalling the robot
is alpha = 0.05, not the smallest alpha available.

Figures: `figures/trajectories.svg` and `.pdf` are the paper's figure rebuilt —
episode 0 of the test set, the nominal arm on the left ending in a collision at
the left edge of an obstacle whose detection was displaced and too small, the
conformal arm on the right routing around the inflated regions, up the corridor
at x = 7.5 m and across at y = 12.5 m, to the goal. The boxes drawn are one
frame, step 20; the trajectory is the whole episode. `figures/tradeoff.svg` and
`.pdf` are the coverage check with its bootstrap intervals and the collision
rate and path length against the coverage level.

### Animation

![Test episode 0 with and without the conformal regions](animations/conformal_regions.gif)

`animations/conformal_regions.mp4` is 20 s at 1280 x 720 and 24 fps; the GIF
above is the same at 640 px and 12 fps, and `conformal_regions_poster.{svg,pdf}`
is its last frame. It plays the episode of `figures/trajectories`, test episode
0, one control step at a time. Left: the robot plans on its raw detections.
Right: it plans on the conformal regions, each detection grown by the calibrated
q = 0.680 m (alpha = 0.10). Every frame shows the true obstacles in grey (the
robot never sees them), that step's detections dashed in orange, on the right
the conformal regions in purple, the path the planner would follow from the
robot's current cell dashed in blue, the trajectory so far, and the robot's
0.7 m square footprint. The left robot strikes an obstacle at step 20, and the
box it struck turns red; the right robot routes around the regions and reaches
the goal at step 48 after 28.56 m. The closing line quotes `results/summary.json`:
168 against 16 collisions over the 200 test episodes, and held-out coverage
0.9037 at the 0.90 target.

`cpnav/replay.py` repeats `run_case_study.py`'s seeded draws (the campaign, the
calibration, the test worlds and the recorded pair), reading the seed and the
sizes from `results/summary.json`. `planner.run_episodes` takes an `on_step`
hook that receives each step's poses, detections, planning regions and
cost-to-go field, and `planner.descend` follows that field from the robot's cell
by the controller's own move rule to give the drawn plan. The replay gives
q = 0.6804527362549031 and a closed-loop coverage of 0.9482 in the conformal arm,
both equal to `results/summary.json`; the script checks q and stops if it
differs. `tests/test_replay.py` checks both numbers, that the hook leaves the run
unchanged, and that the plan's first move is the move the robot makes.

    uv run python animations/make_conformal_regions.py --out animations

`--seed` picks another of the 24 recorded test episodes; `--frames` and `--fps`
set the length. The render needs `ffmpeg` on the `PATH`. It took 28.6 s here, and
a second render gave the same 480 frames and byte-identical poster files.

## Through PERFECT

`run_perfect_campaign.py` generates the calibration data as a real PERFECT
campaign against a live server. The detector configuration is the design
variable — one design per configuration — the clutter band and the seed are the
environment, and a trial is one closed-loop episode that writes back every
detection it made with the ground-truth box beside it. The experiment class and
the two working files it fills are `perfect/examples/conformal-calibration`; the
perception stack and the planner are this directory's `cpnav` package, called
from the trial.

```
cd case-studies/B2-conformal-perception
uv run python run_perfect_campaign.py --submit --url http://127.0.0.1:5001
uv run python run_perfect_campaign.py --collect --url http://127.0.0.1:5001
```

The three designs are the nominal detector, a sharper one (`shift = -0.6`: less
jitter, less shrink) and a degraded one (`shift = 1.0`: twice the jitter and a
further 15 % shrink). The degraded arm is the distribution shift the paper asks
PERFECT to re-run the campaign under.

Recorded run, 2026-09-22, one runner taking the trials one at a time: 3 designs
x 90 environments = 270 trials, 6 min 22 s from the first trial starting to the
last shutting down.

```
detectors: 3 environments: 90 trials: 270
experiments: 270 trials enqueued: 270
finished: 270 of 270

trials collected: 270 states: ['TrialState.SUCCESSFUL|SHUT_DOWN']
SUCCESSFUL trials: 270
episodes: 270 detections: 24704
```

### The calibration, on the campaign's own rows

The split is taken over whole trials, because detections inside one episode see
the same objects from nearby poses and are not exchangeable with each other. The
nominal detector's first twenty seeds in each clutter band calibrate; its last
ten are held out. The two right-hand columns evaluate the same quantile on the
detections the other two designs made.

```
calibrated on 5399 detections of the nominal detector, held out 2441
alpha  target   q (m)   held-out coverage   90% episode-bootstrap interval   sharp   nominal   degraded
  0.3    0.7    0.229    0.721    0.6802 0.7532    0.8701  0.7066  0.016
  0.2    0.8    0.292    0.8341    0.7934 0.8677    0.8715  0.8107  0.0752
  0.15    0.85    0.419    0.8841    0.842 0.9179    0.888  0.8607  0.3981
  0.1    0.9    0.648    0.9156    0.8793 0.9441    0.963  0.905  0.7825
  0.05    0.95    0.804    0.9537    0.931 0.9724    0.9925  0.9513  0.8681
  0.02    0.98    0.928    0.9795    0.9682 0.9886    0.9986  0.98  0.9101
  0.01    0.99    0.985    0.9877    0.9799 0.9935    0.9994  0.9894  0.9261
```

Held-out coverage sits on the target at every level — 0.721 against 0.7, 0.9156
against 0.9, 0.9877 against 0.99 — which is the marginal guarantee doing what it
promises on data the calibration never saw. The sharper detector is covered more
often than asked, and the degraded one is not covered at all at the loose end
(1.6 % at a 70 % target) and still short at the tight end (92.6 % at 99 %). That
is the point of running the campaign under a shift: a quantile calibrated on one
detector does not carry over to a different one, and the campaign is what
measures by how much.

### What the coverage costs

The quantiles above are then spent in the closed loop, on 200 arenas the
campaign never drew, one arm per level plus the raw-detection arm:

```
arm          q (m)  collisions  success  stalls  mean path (m)  mean waits
  nominal     0.0   163    0.185     0      25.86      0.0
  alpha=0.3   0.229  71    0.645     0      27.54      0.04
  alpha=0.2   0.292  61    0.695     0      27.87      0.04
  alpha=0.15  0.419  53    0.735     0      27.92      0.04
  alpha=0.1   0.648  22    0.88      2      28.97      0.02
  alpha=0.05  0.804   4    0.95      6      29.76      0.05
  alpha=0.02  0.928   1    0.945    10      30.52      0.23
  alpha=0.01  0.985   0    0.94     12      30.38      0.75
```

Raw detections collide in 163 of 200 episodes. Inflating them to the 90 %
conformal region brings that to 22, at 3.1 m of extra path; the 99 % region
brings it to none at all, and the cost turns into timeouts — 12 episodes run out
of steps rather than crash. That is the coverage level working as a design
variable.

The campaign's own episodes, which all ran on raw detections, say the same thing
across the grid:

```
detector      sparse   nominal     dense
sharp            0.3     0.633     0.767
nominal          0.5     0.867       0.9
degraded       0.767       1.0       1.0
```

Outputs: `results/perfect/calibration.csv` (24 704 detection rows, one per
detection per frame, with the trial, detector, clutter band and seed beside it),
`results/perfect/episodes.csv` (one row per trial), `results/perfect/coverage.csv`,
`results/perfect/alpha_sweep.csv`, `results/perfect/summary.json`, and the figure
pairs `figures/perfect_coverage.{svg,pdf}` and `figures/perfect_tradeoff.{svg,pdf}`.
Two collections of the same campaign write byte-identical tables and print
identical output.

### What VERITAS makes of it

`veritas/datadriven/report.py` reads the campaign database directly. A trial
counts as a failure when its episode ended in a collision, and `coverage_margin`
— the worst nonconformity score of the trial, negated, so it is positive exactly
when every detection already covered its object with no inflation — is the
number summarised beside it:

```
uv run python datadriven/report.py --db campaign.db --out . \
    --metric coverage_margin --failure-metric collisions --failure-above 0.0 \
    --group-by design
```

| design | trials | failures | rate | exact interval | Wilson interval | exact upper | trials for target |
|---|---|---|---|---|---|---|---|
| degraded | 90 | 83 | 0.9222 | [0.8463, 0.9682] | [0.8481, 0.9618] | 0.9629 | 1985 |
| nominal | 90 | 68 | 0.7556 | [0.6536, 0.84] | [0.6575, 0.8327] | 0.8283 | 1657 |
| sharp | 90 | 51 | 0.5667 | [0.458, 0.6708] | [0.4636, 0.6642] | 0.6554 | 1282 |

| design | n | mean coverage margin | min | violated | 0.05 quantile |
|---|---|---|---|---|---|
| degraded | 90 | -1.1116 | -1.7732 | 1.0 | -1.553 |
| nominal | 90 | -0.7542 | -1.3594 | 1.0 | -1.1827 |
| sharp | 90 | -0.5533 | -1.0782 | 1.0 | -0.9994 |

The three exact intervals for the collision rate are ordered and the outer two
do not overlap, so 90 episodes per detector are enough to separate the sharp
detector from the degraded one at 95 % confidence. The coverage margin is
negative in every trial of every design: there is always at least one detection
that misses its object outright, which is why the region has to be inflated at
all. The report, its figure pair and the campaign database are in
`veritas/datadriven/results/conformal/`.

## What each piece is

* `cpnav/detector.py` — a seeded noise model on the true boxes: centre jitter
  that grows with range, a multiplicative size factor below 1, and a fixed
  fraction of objects with a much heavier under-estimation.
* `cpnav/world.py` — random axis-aligned boxes in a square arena; ground
  truth is taken from the sampled boxes.
* `cpnav/campaign.py` — the nominal closed loop run over random worlds.
* `cpnav/planner.py` — a grid wavefront planner on a 0.5 m occupancy grid,
  point-goal, square robot footprint.
* `cpnav/tradeoff.py` — a grid sweep over alpha, the TRADES-X-style design
  variable, reporting the coverage bought and the conservativeness it costs
  at each value.

The distribution-shift knob `detector.detect(..., shift=s)` scales the jitter
by `1 + s` and lowers the mean size factor; `run_case_study.py` does not call
it with a nonzero shift.

## Reading the numbers

**Per-detection coverage is not per-episode safety.** The conformal guarantee
is marginal over detections. An episode contains many detections, so a
collision rate over episodes is not bounded by alpha: the conformal arm still
collides in 16 of 200 episodes at alpha = 0.10, against a per-detection
miscoverage of 0.10. Lowering alpha lowers the collision rate, which is why
the sweep, not the theory alone, is what fixes the operating point.

**The calibration data and the conformal closed loop are not the same
distribution.** Calibration runs the *nominal* planner; once the inflated
boxes change the plan, the robot visits different states, so the
exchangeability that split CP assumes is broken by the very intervention it
enables. The script reports the realized coverage inside the conformal
closed loop beside the held-out coverage so the size of that gap is visible
— this is the problem the navigation-safety construction of Mei et al.
addresses, by drawing the calibration set from the closed-loop states the
robot will actually visit.

## Numerics

Everything numeric is whole-array numpy over a batch whose leading axis is the
episode: the detector, the rasterizer, the cost-to-go relaxation, the collision
sweep test, the conformal quantile and coverage, and the bootstrap. The alpha
sweep stacks all arms along that same episode axis and runs them in one call.
The only interpreter loops are over control steps, over relaxation sweeps, over
the eight neighbour offsets, and one explicitly labelled brute-force oracle in
`tests/test_planner.py`.

## Citations

Both are taken from the camera-ready's own bibliography
(`manuscript/.../references.bib`, keys `angelopoulos2023conformal` and
`mei2026perceive`).

- A. N. Angelopoulos and S. Bates, *Conformal prediction: A gentle
  introduction*, Foundations and Trends in Machine Learning, vol. 16, no. 4,
  pp. 494-591, 2023. The split conformal procedure and the
  `ceil((n + 1)(1 - alpha))` finite-sample correction used in
  `cpnav/conformal.py`.
- Z. Mei, A. Dixit, M. Booker, E. Zhou, M. Storey-Matsutani, A. Z. Ren,
  O. Shorinwa and A. Majumdar, *Perceive with confidence: Statistical safety
  assurances for navigation with learning-based perception*, The International
  Journal of Robotics Research, vol. 45, no. 6, pp. 938-967, 2026. The
  end-to-end navigation-safety construction the paper follows, and the source
  of the closed-loop distribution-shift caveat above. (The paper's text refers
  to this work by its second author; the bibliography entry is first-authored
  by Mei.)
