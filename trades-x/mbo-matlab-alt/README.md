# MBO, MATLAB alternates

Reference only. These are MATLAB versions of pieces of the model-based
optimization stage, written before the Julia package in `../mbo/` took over.
Nothing in TRADES-X calls them and none of them is run by the gates.

| file | what it does |
|---|---|
| `MatSensorTrade.m` | sensor-suite trade study driven from MATLAB |
| `pareto.m` | the `prtp` Pareto filter; `tradesx/pareto.py` ports it |
| `rosbageval_perfect.m` | reads run bags and computes path length, time to completion and cumulative elevation gradient; `tradesx/bag_metrics.py` ports it |
| `test.m` | scratch |

Moved here from `perfect/perfect_MBO/MBO-Matlab-alt/` on 2026-09-22, unchanged.
A fuller set of the same MATLAB workbench lives under `sysml/workbench/`.
