# Case study A2: risk-sensitive path planning with PERFECT

This realises Section IV-A.2 of the IDDMBSE camera-ready, "Risk-Sensitive Path
Planning with PERFECT":

> The risk-sensitive planner RA-RRT\* casts navigation as a stochastic
> shortest-path problem and minimizes the sum of per-segment Conditional
> Value-at-Risk (CVaR), retaining the asymptotic optimality of RRT\* while
> hedging against tail events. Across four noise levels and three risk levels
> over 50 runs, it attains lower worst-case path length and markedly fewer
> planner failures than RRT\* at a modest computation premium, with the
> risk-averse policy hugging safer routes as the environment hardens. PERFECT
> supplies the distributed campaign behind these comparisons, treating the
> planner as a behavioral design variable to evaluate at scale.

**This code was written for this release.** The repository carried no
implementation of RA-RRT\*, and the published results of Enwerem, Noorani,
Baras and Sadler (arXiv:2408.08668, CDC 2024) were produced elsewhere. What
follows is an independent implementation built to the description above, run on
a synthetic world generator, reporting what it produced. It is not a
reproduction of the paper's numbers and should not be read as one.

Synthetic here: the world generator (random discs), the segment-cost noise
model, the traversal budget that defines a failure. Real here: the planner, the
risk measures, the campaign and every number in the table.


## The problem

A stochastic shortest-path problem. A path is a sequence of straight segments
`p_0 ... p_N`. Traversing segment `k` costs a random variable `L_k`, so a path
has a cost distribution rather than a cost, and "shortest" has to be replaced by
a functional of that distribution.

For a cost `Y` and a confidence level `alpha`,

    VaR_alpha(Y)  = the alpha-quantile of Y
    CVaR_alpha(Y) = E[Y | Y >= VaR_alpha(Y)]
                  = inf_z { z + E[Y - z]^+ / (1 - alpha) }

(the second line is the Rockafellar-Uryasev form, and is what `rarrt/risk.py`
evaluates, at `z = VaR_alpha`, where the objective attains its minimum on an
empirical distribution). Risk lives in the upper tail because `Y` is a cost:
`alpha = 0` gives the mean and `alpha -> 1` the worst case.

The three planners compared here differ only in the functional applied to the
segment cost distribution:

| policy | edge cost | what it is |
|---|---|---|
| `rrtstar` | the Euclidean length `E[L_k]` under no noise | plain RRT\*, the paper's baseline |
| `neutral` | `E[L_k]` | risk-neutral RA-RRT\*, i.e. CVaR at `alpha = 0` |
| `cvar0.1`, `cvar0.5`, `cvar0.9` | `CVaR_alpha(L_k)` | RA-RRT\* at the paper's three risk levels |

The path objective is the **sum** of per-segment CVaRs, as the manuscript says.
That matters: CVaR is subadditive, so the sum is an upper bound on the CVaR of
the total cost, and unlike the total's CVaR it is additive over segments. RRT\*
needs an additive cost to keep a cost-to-come per node and to compare a rewired
subpath against the old one, so the additive surrogate is what makes the
optimal-substructure argument -- and therefore RRT\*'s asymptotic optimality
argument -- go through at all. `rarrt/rrtstar.py` uses the ordinary RRT\*
cost-to-come bookkeeping over this additive cost; nothing about ChooseParent,
Rewire or the near radius changes.


## The noise model, and where it departs from the paper

The paper's segment cost is `L_k = c_k + C_k` with `C_k ~ N(0, s_k^2)`
exogenous: obstacle proximity does not enter it, and the paper names
obstacle-coupled noise as future work. That model cannot produce the
manuscript's figure claim. With an exogenous Gaussian,

    CVaR_alpha(c_k + C_k) = c_k + s_k * phi(z_alpha) / (1 - alpha),

so the risk term is a constant per segment: the risk-averse planner prefers
*fewer* segments, not safer ones. If instead `s_k` scales with `c_k`, the whole
cost scales uniformly and the optimal path does not move at all. Either way the
route does not change shape, and "hugging safer routes as the environment
hardens" cannot happen.

So this case study uses the obstacle-coupled model the manuscript's claim
requires. For a segment of length `L` whose smallest clearance to an obstacle is
`d`:

    cost = L * max(0, 1 + sigma * (Z + kappa * E * 1{U < p(d)}))
    p(d) = p_max * exp(-d / d_hazard)
    Z ~ N(0,1),  E ~ Exp(1),  U ~ U(0,1)

The Gaussian part is ordinary traversal noise. The exponential part is a hazard
-- a slip, a snag, a re-plan -- whose chance rises as the segment passes closer
to clutter. `sigma` is the noise level and scales both parts.

Two choices worth stating because they decide the outcome:

* The hazard is **rare and severe** (`p_max = 0.15`, `kappa = 20`,
  `d_hazard = 2.0 m`), not frequent and moderate. A frequent hazard is a shift
  in the mean, which the risk-neutral planner already avoids, leaving the risk
  level with nothing to do. A first pilot with `p_max = 1`, `kappa = 4` showed
  exactly that: risk-neutral and `alpha = 0.9` produced nearly the same route.
  A tail event is what CVaR is for, so the model was set to produce one.
* The multiplier is clipped at zero so costs stay non-negative. At the largest
  noise level (`sigma = 0.5`) the Gaussian part falls below `-1` about 2.3 % of
  the time, so that clip is active there.

Because the noise is multiplicative and CVaR is positively homogeneous, the edge
cost factors as `L * g(d)` with `g(d) = CVaR_alpha(multiplier at clearance d)`.
The risk level reweights the metric by clearance. That is the whole mechanism.


## Environments, noise levels, risk levels

Three clutter levels, discs of radius 1.2 to 4.0 m placed by a Boolean model in
a 64 x 64 m square, start at `(-28, -28)`, goal at `(28, 28)`, straight-line
distance 79.2 m. The obstacle count comes from the coverage target; the measured
free fraction is what the generator actually achieved on a 512 x 512 grid:

| environment | coverage target | obstacles (seed 0) | measured free fraction |
|---|---|---|---|
| easy | 0.08 | 12 | 0.935 |
| medium | 0.16 | 28 | 0.832 |
| hard | 0.26 | 48 | 0.758 |

Four noise levels `sigma` in `{0.01, 0.05, 0.1, 0.5}` and three risk levels
`alpha` in `{0.1, 0.5, 0.9}`, both taken from the paper's sweep, plus the two
reference policies. The paper's noise is additive in metres and this one is
multiplicative, so the four values match by number, not by units.

Every run index gets its own world, shared by all policies and noise levels at
that index, so comparisons across policies are paired.


## Metrics

* **success rate** -- the planner returned a path. It is 1.000 in all 3000 runs
  below, and it cannot discriminate between the policies even in principle: with
  a shared seed the sampling, steering and collision checks are identical across
  policies, so the three planners grow the **same set of nodes** and differ only
  in the parent structure. (`tests/test_rrtstar.py` pins this.) Any difference
  in the returned path is attributable to the risk functional and nothing else.
* **failure rate** -- the useful failure measure, defined on execution: the
  planned path is traversed 400 times under **fresh** noise, independent of the
  samples the planner optimised against, and a traversal that costs more than
  `1.5 x 79.2 = 118.8 m` is a failure. A run with no path counts all 400 of its
  executions as failures. The budget factor 1.5 was fixed once, from a pilot, so
  that the rates are neither zero nor saturated; it is absolute and
  policy-independent, which matters below.
* **hazard rate** -- the fraction of executions that hit at least one hazard.
  This is the analogue of the collision count in the report's Gazebo variant,
  and it is the metric a longer detour cannot game.
* **mean path length** -- the mean over runs of the planned path's Euclidean
  length. This is the premium the manuscript refers to.
* **worst-case path length** -- the **95th percentile** of the realised
  traversal cost, pooled over all 400 x 50 executions of a cell. The pooled
  maximum is reported alongside it.
* **plan time** -- wall clock per planner run.


## How PERFECT would run this

The campaign is 3 environments x 4 noise levels x 5 policies x 50 runs = 3000
planner runs. Mapped onto PERFECT's own objects (`perfect/README.md`):

| here | PERFECT |
|---|---|
| a policy (`rrtstar` ... `cvar0.9`) | a `ComponentImplementation` of the planner component; one `Design` each, `designs create <name> <planner> -i` |
| a (clutter, noise) pair | an `Environment`, `environments create_explicit <name> '{"coverage": ..., "sigma": ...}' -t <tag>` |
| a cell of the grid | an `Experiment`, created by tag matching: `experiments create <design-tag> <env-tag>` gives 5 x 12 = 60 experiments |
| one run with its seed | a `Trial` of that experiment, 50 per experiment |
| the process pool | the RQ workers and the runner, `experiments run <tag>` enqueueing to Redis, results in the SQLite database |

**This brief does not start PERFECT.** Nothing here was run through a PERFECT
server, worker or runner; a `multiprocessing` pool stands in for the workers so
the case study runs on one machine with no Redis and no ROS. The table above is
the mapping, not a record of a PERFECT run.


## Results

Recorded run, 2026-09-22, 16 worker processes, 3000 runs in 109 s.

```
failure = execution over the traversal budget of 118.8 m, or no path found; worst case = 95th percentile of realised cost

easy environment
 sigma    policy  success  failure  hazard  mean len  worst p95      max  clearance   plan s
  0.01   rrtstar      1.0      0.0   0.463     80.09       83.2     92.4       0.76     0.21
  0.01   neutral      1.0      0.0   0.456     80.12       83.1     91.7       0.91    0.392
  0.01   cvar0.1      1.0      0.0   0.447     80.14       83.0     91.9       0.93    0.796
  0.01   cvar0.5      1.0      0.0   0.425     80.19       83.0     91.9       1.18    0.807
  0.01   cvar0.9      1.0      0.0   0.331     80.89       83.7     93.9       2.17    0.806
  0.05   rrtstar      1.0   0.0009   0.463     80.09       94.1    137.2       0.76    0.175
  0.05   neutral      1.0   0.0004   0.374      80.5       90.6    131.8        1.7    0.404
  0.05   cvar0.1      1.0   0.0004   0.369     80.54       90.5    131.8        1.8    0.833
  0.05   cvar0.5      1.0   0.0004   0.328     80.93       89.5    128.8       2.18    0.833
  0.05   cvar0.9      1.0   0.0001   0.233     83.12       90.4    121.5        3.3    0.786
   0.1   rrtstar      1.0   0.0215   0.463     80.09      108.0    193.1       0.76    0.184
   0.1   neutral      1.0   0.0067   0.321     80.99       98.1    175.1       2.27    0.399
   0.1   cvar0.1      1.0   0.0063   0.314     81.05       97.9    182.9       2.37    0.813
   0.1   cvar0.5      1.0   0.0067    0.27     81.67       96.9    188.6       2.77    0.844
   0.1   cvar0.9      1.0   0.0036   0.214     84.44       95.7    154.1       3.58    0.872
   0.5   rrtstar      1.0   0.2463   0.463     80.09      219.0    640.3       0.76    0.166
   0.5   neutral      1.0   0.0872   0.227     83.46      142.2    439.6       3.41    0.368
   0.5   cvar0.1      1.0   0.0868   0.227     83.48      142.9    518.1       3.41     0.79
   0.5   cvar0.5      1.0   0.0831   0.218     84.07      139.7    439.3       3.54    0.796
   0.5   cvar0.9      1.0   0.0729   0.191     87.56      132.5    557.5       3.76    0.806

medium environment
 sigma    policy  success  failure  hazard  mean len  worst p95      max  clearance   plan s
  0.01   rrtstar      1.0      0.0   0.625     80.46       84.5     96.5       0.28    0.172
  0.01   neutral      1.0      0.0   0.626     80.49       84.2     94.8       0.34    0.377
  0.01   cvar0.1      1.0      0.0   0.622      80.5       84.2     94.8       0.35    0.755
  0.01   cvar0.5      1.0      0.0   0.619     80.56       84.2     92.8        0.4    0.745
  0.01   cvar0.9      1.0      0.0   0.526     81.46       85.0     92.7       1.12    0.775
  0.05   rrtstar      1.0    0.003   0.625     80.46       98.8    158.8       0.28    0.205
  0.05   neutral      1.0   0.0008   0.555     81.02       94.8    130.3        0.9    0.403
  0.05   cvar0.1      1.0   0.0008    0.55     81.07       94.6    144.1       0.93    0.818
  0.05   cvar0.5      1.0   0.0006   0.522     81.51       94.2    136.0       1.15    0.803
  0.05   cvar0.9      1.0   0.0008   0.404     84.83       95.1    128.0       2.16    0.768
   0.1   rrtstar      1.0   0.0438   0.625     80.46      116.7    236.8       0.28    0.212
   0.1   neutral      1.0   0.0168   0.518     81.57      106.4    205.5       1.21    0.397
   0.1   cvar0.1      1.0   0.0168   0.512     81.66      106.7    175.5       1.25    0.752
   0.1   cvar0.5      1.0   0.0152   0.454     82.87      105.8    179.8       1.74    0.802
   0.1   cvar0.9      1.0   0.0133   0.385     86.53      105.4    176.1       2.37    0.801
   0.5   rrtstar      1.0   0.3692   0.625     80.46      261.5    860.4       0.28    0.197
   0.5   neutral      1.0   0.1741   0.397     85.35      177.0    527.4       2.28    0.384
   0.5   cvar0.1      1.0   0.1753   0.395     85.37      176.1    527.4       2.28    0.714
   0.5   cvar0.5      1.0   0.1752   0.388     86.16      176.9    490.4       2.35    0.768
   0.5   cvar0.9      1.0   0.1792   0.379     89.82      170.4    579.4       2.51    0.681

hard environment
 sigma    policy  success  failure  hazard  mean len  worst p95      max  clearance   plan s
  0.01   rrtstar      1.0      0.0   0.755      81.9       89.0     99.7       0.11    0.178
  0.01   neutral      1.0      0.0   0.757     81.94       88.6     99.4       0.19    0.313
  0.01   cvar0.1      1.0      0.0   0.758     81.95       88.5     99.4       0.19    0.587
  0.01   cvar0.5      1.0      0.0   0.754      82.0       88.6     98.6       0.22    0.656
  0.01   cvar0.9      1.0      0.0    0.69     83.03       89.1     99.8        0.5    0.614
  0.05   rrtstar      1.0   0.0058   0.755      81.9      103.7    148.5       0.11    0.195
  0.05   neutral      1.0   0.0028   0.723     82.42      100.2    141.6       0.36    0.327
  0.05   cvar0.1      1.0   0.0031    0.72     82.51      100.3    141.6       0.37    0.611
  0.05   cvar0.5      1.0   0.0024   0.682     83.15       99.5    135.4       0.58    0.653
  0.05   cvar0.9      1.0   0.0026   0.623     86.51      101.5    137.9       1.13    0.629
   0.1   rrtstar      1.0   0.0722   0.755      81.9      124.5    213.2       0.11    0.182
   0.1   neutral      1.0   0.0365   0.679     83.26      114.8    194.4       0.62    0.301
   0.1   cvar0.1      1.0   0.0374   0.675     83.34      115.0    194.4       0.64    0.556
   0.1   cvar0.5      1.0   0.0343   0.651     84.22      113.9    194.2       0.93    0.605
   0.1   cvar0.9      1.0   0.0364   0.597     89.18      115.3    196.9        1.3    0.557
   0.5   rrtstar      1.0   0.4913   0.755      81.9      292.2    730.1       0.11    0.171
   0.5   neutral      1.0   0.3232   0.613     87.27      218.2    610.8       1.16    0.305
   0.5   cvar0.1      1.0     0.32   0.614     87.31      217.6    610.8       1.16    0.526
   0.5   cvar0.5      1.0   0.3181   0.599     88.67      218.0    618.7       1.29    0.619
   0.5   cvar0.9      1.0   0.3367   0.585     93.29      210.6    564.5       1.47    0.532

figures: ['failure_and_worstcase.pdf', 'failure_and_worstcase.svg', 'paths_by_environment.pdf', 'paths_by_environment.svg', 'premium_against_protection.pdf', 'premium_against_protection.svg']
```

### What the numbers say

**Against plain RRT\*, the manuscript's claim holds and is large.** At the
highest noise level, taking `cvar0.9` against `rrtstar`:

| environment | worst-case p95 | failure rate | hazard rate | mean length | plan time |
|---|---|---|---|---|---|
| easy | 219.0 -> 132.5 m (x0.61) | 0.246 -> 0.073 (x0.30) | 0.463 -> 0.191 (x0.41) | +9.3 % | x4.9 |
| medium | 261.5 -> 170.4 m (x0.65) | 0.369 -> 0.179 (x0.49) | 0.625 -> 0.379 (x0.61) | +11.6 % | x3.5 |
| hard | 292.2 -> 210.6 m (x0.72) | 0.491 -> 0.337 (x0.69) | 0.755 -> 0.585 (x0.77) | +13.9 % | x3.1 |

Lower worst-case path length: yes, by 28 to 39 %. Fewer failures: yes, by 31 to
70 %. A modest path-length premium: 9 to 14 %. The computation premium is a
factor of 3 to 5 in this implementation -- but that number is about the
implementation, not the method: it is the cost of an empirical CVaR over 2048
samples per candidate edge, where the paper evaluates a Gaussian CVaR in closed
form.

**The advantage widens with the noise level, strongly.** At `sigma = 0.01` every
policy is within 0.8 m of every other on worst-case length and no policy ever
fails. In the easy world a gap opens at `sigma = 0.05` (94.1 m for `rrtstar`
against 90.4 for `cvar0.9`), widens at 0.1 (108.0 against 95.7) and is large at
0.5 (219.0 against 132.5). This is the clearest effect in the table.

**The advantage does not widen from the easy to the hard environment -- it
narrows.** The ratio of `cvar0.9` worst-case length to `rrtstar` worst-case
length at `sigma = 0.5` is 0.61 (easy), 0.65 (medium), 0.72 (hard), and the
failure-rate ratio goes 0.30, 0.49, 0.69 the same way. The absolute gap in
worst-case length is roughly constant (87, 91, 82 m). The reason is visible in
`figures/paths_by_environment.*`: risk aversion works by detouring into open
space, and the hard environment has less open space to detour into. The
manuscript's figure caption says the advantage widens from the easy to the hard
environment; under this model and these metrics it does not. That is the honest
result, and it is a property of the model, not a measurement of the paper's
system.

**Between the risk levels the differences are small, and one of them reverses.**
At `sigma = 0.5`, going from `neutral` to `cvar0.9` lowers the worst-case length
(142.2 -> 132.5 easy, 177.0 -> 170.4 medium, 218.2 -> 210.6 hard) and lowers the
hazard rate everywhere (0.227 -> 0.191, 0.397 -> 0.379, 0.613 -> 0.585), but the
failure rate improves only in the easy environment (0.0872 -> 0.0729) and gets
slightly worse in the medium (0.1741 -> 0.1792) and hard (0.3232 -> 0.3367)
ones. The two metrics disagree because the budget is absolute while the
risk-averse path is 5 to 7 % longer: at high clutter the extra length costs more
budget than the lighter tail saves. Raising the risk level buys tail protection
and pays for it in nominal length, and against a fixed absolute deadline that
trade can come out negative. The hazard rate, which a detour cannot game, is
lower for `cvar0.9` than for both `rrtstar` and `neutral` in all twelve cells;
it is not exactly monotone in `alpha` (four cells wiggle upward, by at most
0.0014).

**Clearance behaves as the mechanism predicts.** The mean smallest clearance
along the planned path rises monotonically with the risk level in all twelve
cells -- at `sigma = 0.5`, 0.76 -> 3.41 -> 3.76 m (easy), 0.28 -> 2.28 -> 2.51
(medium), 0.11 -> 1.16 -> 1.47 (hard) -- and so does the mean planned length.
"Hugging safer routes" is reproduced; it is the benefit of doing so that does
not widen with clutter.


## Figures

`figures/paths_by_environment.{svg,pdf}` -- the paper-figure analogue. Three
panels, easy to hard. Black discs are obstacles, the thin grey lines are the
plain RRT\* tree -- all three policies grow the same node set from the same
seed, but wire it differently -- the green dot is the start and the red star the
goal. Plain RRT\* (dark grey) runs almost straight down the diagonal and grazes
obstacles: smallest clearance 0.61 m in the easy world, 0.18 m in the medium,
0.00 m in the hard. Risk-neutral (blue) and risk-averse (red) both bow away from
the clutter, and in these three examples they share the same bottleneck (3.48,
3.28 and 1.45 m); the red path is the longer of the two in all three panels
(87.3 against 83.4 m easy, 87.8 against 85.2 medium, 91.9 against 86.5 hard).
The legend gives each path's length and smallest clearance.

`figures/failure_and_worstcase.{svg,pdf}` -- failure rate (top) and worst-case
p95 path length (bottom) against the noise level, one column per environment.
The plain RRT\* curve separates sharply above `sigma = 0.05`. The four
risk-aware curves lie almost on top of each other; that near-coincidence is a
result, not a plotting fault.

`figures/premium_against_protection.{svg,pdf}` -- at `sigma = 0.5`, worst-case
p95 against mean planned length, one point per policy. This is the trade the
manuscript describes: moving right (a longer nominal path) buys moving down (a
lighter tail), and the risk level is the dial.


## Run it

```
cd case-studies/A2-risk-sensitive-planning
uv sync --all-extras
uv run pytest -q
uv run python run_case_study.py
```

The campaign takes about 105 s on 16 processes; `campaign.yaml` holds the grid
and the model parameters, including the pool size. Outputs are
`results/campaign.csv` (one row per run), `results/summary.json` (per-cell
aggregates plus the configuration) and the three figure pairs.

Everything is seeded. Two runs of `run_case_study.py` produce byte-identical
values in every column except `plan_time`; `tests/test_campaign.py` pins that on
a small grid.


## Implementation notes

* **Common random numbers.** A planner run draws one fixed set of 2048 noise
  samples and reuses it for every candidate segment, so the edge cost is a
  deterministic function of (length, clearance). RRT\* requires this: an edge
  re-costed during Rewire must return the number it returned during
  ChooseParent. The CRN seed is shared across policies at a given run index, so
  the risk levels are compared on the same sample set.
* **Why 2048 samples.** At 512 the edge-cost estimate had a per-seed spread of
  about 2.0 on values of 2 to 15 (20 seeds, clearances 0 to 8 m at
  `sigma = 0.5`), i.e. 15 to 20 % of the value; at 2048 it is about half that,
  and the mean over 20 seeds sits within 5 % of a two-million-sample reference.
  `tests/test_rrtstar.py` checks that last statement.
* **Vectorisation.** The RRT\* iteration loop is sequential because the tree is
  grown incrementally, but everything inside it is whole-array numpy: the
  nearest-neighbour query over all nodes, the near-set mask, the exact
  segment-to-disc clearance over all (candidate edge, obstacle) pairs, the 2048
  noise samples per candidate edge, and the CVaR over them. Rewire cost
  propagation walks the subtree one depth level at a time with a masked update.
  Path execution draws all 400 x (segments) realisations in one array.
* **Collision checking is exact,** not sampled along the segment: the closest
  point of a segment to a disc centre is the clamped projection, and the
  distance-to-boundary of a box is concave inside it, so its minimum over a
  segment is at an endpoint. The robot is a point.
* **Planner settings.** 1500 iterations, a 3 m steering step, 5 % goal bias, and the
  near radius `min(gamma * sqrt(log n / n), 2 * step)` with `gamma` from the free-space
  area. The goal is connected at the end from whichever node within 6 m has a
  collision-free straight edge to it and the lowest total cost.
* **No cycles can appear in Rewire.** Edge costs are strictly positive, so a
  descendant of a node always has a larger cost-to-come and can never pass the
  rewire test against its own ancestor.


## Tests

`uv run pytest -q` -- 37 tests. The ones that matter:

* CVaR of 2 000 000 Gaussian samples against `phi(z_alpha)/(1-alpha)` at five
  levels, tolerance 0.01; VaR against `Phi^-1(alpha)`, same tolerance; EVaR
  against `mu + s*sqrt(2 log(1/(1-alpha)))`, tolerance 0.05.
* CVaR at least the mean, strictly increasing in `alpha`, above VaR, below EVaR,
  positively homogeneous, and the batched form equal to a row-by-row oracle.
* RRT\* finds a path in an empty world and its cost falls towards the
  straight-line distance as iterations rise (200, 600, 1800), within 2 % at 1800
  -- the asymptotic-optimality sanity check.
* The cost the planner reports equals the cost of the path it returns,
  recomputed from the geometry. This is the check on the ChooseParent and Rewire
  bookkeeping.
* Every segment of a returned path is collision free; a segment through a disc
  has exactly the expected negative clearance; a segment passing above one has
  exactly the expected positive clearance.
* The campaign runner on a 2 x 1 x 2 x 2 grid writes the CSV with the expected
  columns, and reproduces exactly on a second run.


## What is not here

The long-form report's Gazebo variant -- a risk-aware potential field over noisy
occupancy grids at inflation radii `{0.1, 0.5, 0.6, 0.7, 0.9, 0.95, 0.99}` on
two environments, measuring path distance, collisions and goal reach -- is not
reproduced. It needs a Gazebo run, and no simulator was started for this case
study. EVaR is implemented in `rarrt/risk.py` and tested but is not used by the
planner; the paper does not use it either.


## Sources

* C. Enwerem, E. Noorani, J. S. Baras and B. M. Sadler, "Robust Stochastic
  Shortest-Path Planning via Risk-Sensitive Incremental Sampling",
  arXiv:2408.08668, 63rd IEEE Conference on Decision and Control, 2024. The
  risk-sensitive formulation, the CVaR definitions, the near-radius rule and the
  sweep over four noise levels and three risk levels.
* S. Karaman and E. Frazzoli, "Sampling-based algorithms for optimal motion
  planning", IJRR 30(7), 2011. RRT\* and the gamma * (log n / n)^(1/2) near
  radius.
* R. T. Rockafellar and S. Uryasev, "Optimization of conditional value-at-risk",
  Journal of Risk 2(3), 2000. The inf-over-z form that `rarrt/risk.py` evaluates.
* The IDDMBSE camera-ready, `sections/case_studies.tex`, Section IV-A.2, and
  `perfect/README.md` for the Design/Environment/Experiment/Trial mapping.
