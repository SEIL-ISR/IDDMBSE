# Case study B2 — Robust perception via conformal prediction

This directory was built for this release. The paper's Section IV-B.2 describes
the demonstration; no code for it existed in the repository, so it is rebuilt
here to that description, with a synthetic detector and a synthetic world in
place of the lab's Isaac Sim range and YOLOv8 stack. Everything the paper
claims about the *method* is reproduced and measured; nothing here was run on
hardware or in Isaac Sim. What is synthetic and what would be real in the lab
pipeline is spelled out below.

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

A 20 m by 20 m arena with axis-aligned rectangular obstacles stands in for the
contested-terrain range. A point-goal navigation task runs a closed loop: at
every control step the robot detects the obstacles it can see, optionally
inflates each detection to its conformal region, rasterizes the result into an
occupancy grid, recomputes the cost-to-go to the goal, moves one cell, and is
checked for collision against the **true** obstacles. Five steps:

1. **Campaign** (`cpnav/campaign.py`). Run the nominal closed loop over
   randomly drawn worlds and record, for every frame, one row per detection
   with the ground-truth box beside it. This is the stand-in for a PERFECT
   campaign; the table it writes has the shape a PERFECT Trial result would
   carry (flat per-detection rows keyed by episode and frame), so a real
   campaign export drops in unchanged. Written to `results/campaign.csv`.
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

## Results

One seeded run, `SEED = 20260922`, measured 2026-09-22. `uv run pytest -q` is
19 passed. The script took between 104 s and 121 s over four runs of this
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

## What is synthetic, and what would be real

| here | in the lab pipeline |
|---|---|
| `cpnav/detector.py`: a seeded noise model on the true boxes — centre jitter that grows with range, a multiplicative size factor below 1, and a fixed fraction of objects with a much heavier under-estimation | YOLOv8 + DeepSORT running inside the SEIL-R2 Nav2 stack, its errors whatever they are |
| `cpnav/world.py`: random axis-aligned boxes in a square arena | the contested-terrain Isaac Sim range |
| ground truth taken from the sampled boxes | ground-truth 3-D asset attributes read out of Isaac Sim |
| `cpnav/campaign.py`: the nominal closed loop run over random worlds | a PERFECT campaign driving the full perception-and-planning stack across the range at scale, and re-generating it under deliberate shifts in lighting, clutter and terrain |
| `cpnav/planner.py`: a grid wavefront planner on a 0.5 m occupancy grid, point-goal, square robot footprint | Nav2, with the conformalized boxes entering through a costmap plugin |
| `cpnav/tradeoff.py`: a grid sweep over alpha | a TRADES-X design-space exploration stage with 1 - alpha as one design variable among others |

The distribution-shift knob is exposed but not exercised by the reproduction
script: `detector.detect(..., shift=s)` scales the jitter by `1 + s` and lowers
the mean size factor, which is the synthetic analogue of PERFECT re-running the
campaign under heavier clutter or worse lighting. Re-calibrating under shift is
left to whoever has the real campaign data.

## Two honest caveats

**Per-detection coverage is not per-episode safety.** The conformal guarantee
is marginal over detections. An episode contains many detections, so a
collision rate over episodes is not bounded by alpha, and the numbers above
show that directly: the conformal arm still collides in 16 of 200
episodes at alpha = 0.10, against a per-detection miscoverage of 0.10. Lowering alpha lowers the collision rate, which is why the sweep
and not the theory is what fixes the operating point.

**The calibration data and the conformal closed loop are not the same
distribution.** Calibration runs the *nominal* planner; once the inflated boxes
change the plan, the robot visits different states, so the exchangeability that
split CP assumes is broken by the very intervention it enables. The script
reports the realized coverage inside the conformal closed loop beside the
held-out coverage so the size of that gap is visible. This is the problem the
navigation-safety construction of Mei et al. addresses, and it is the reason
the paper insists the calibration set be drawn from the closed-loop states the
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
