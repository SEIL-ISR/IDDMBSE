# Full 2^13 - 1 = 8191 design enumeration of the sensor-suite study.
#
# The recorded run capped the design size at 6 sensors, which is 4095 designs.
# mbo/run_mbo.jl 13 lifts that cap and writes data/full_enumeration_4met.csv
# and data/pareto_full.csv. This script reproduces the Pareto count from the
# CSV with the Python filter, checks the Python oracles against the Julia ones
# on the three order-independent metrics, and looks up the seven designs the
# 2024 PERFECT campaign simulated.

import itertools
import pathlib
import numpy as np

from tradesx.pareto import non_dominated, non_dominated_matlab_compat
from tradesx import sensitivity as sens

here = pathlib.Path(__file__).parent
data = here / "data"

sense = [-1, -1, -1, -1]
n_slots = 13

full = np.loadtxt(data / "full_enumeration_4met.csv", delimiter=",")
capped = np.loadtxt(data / "plot4met.csv", delimiter=",")
rec_idx = np.loadtxt(data / "pareto_designs.csv", delimiter=",").astype(int)
jl_full_idx = np.loadtxt(data / "pareto_full.csv", delimiter=",").astype(int)

print("full enumeration rows:", full.shape[0])
print("capped enumeration rows:", capped.shape[0])
print("first 4095 rows of the full run equal plot4met.csv:",
      np.array_equal(full[:capped.shape[0]], capped))

# ------------------------------------------------------------------
# the selection matrix, in the order Combinatorics.powerset produces
# (by size, then lexicographic), so row r of the CSV is subsets[r]
subsets = [s for k in range(1, n_slots + 1)
           for s in itertools.combinations(range(n_slots), k)]
rows = np.repeat(np.arange(len(subsets)), [len(s) for s in subsets])
cols = np.fromiter(itertools.chain.from_iterable(subsets), dtype=int)
selection = np.zeros((len(subsets), n_slots), dtype=float)
selection[rows, cols] = 1.0

# a design id is the decimal encoding evalpoly(2, reverse(design)), so slot i
# of 13 carries weight 2**(13 - i)
weights = 2.0 ** np.arange(n_slots - 1, -1, -1)
design_ids = (selection @ weights).astype(int)

# ------------------------------------------------------------------
# the Python oracles against the Julia ones, on the three metrics that do not
# depend on evaluation order (coverage does: effective_coverage_oracle mutates
# the catalogue, so it is not compared here)
py = sens.metrics(selection)
print("cost max abs difference vs Julia:", np.abs(py[:, 0] - full[:, 0]).max())
print("RAM max abs difference vs Julia:", np.abs(py[:, 1] - full[:, 1]).max())
print("power max abs difference vs Julia:", np.abs(py[:, 2] - full[:, 2]).max())

# ------------------------------------------------------------------
# Pareto counts
mask_f, idx_f = non_dominated(full, sense)
mask_c, idx_c = non_dominated_matlab_compat(full, sense)
mask_k, idx_k = non_dominated(capped, sense)

print()
print("full 8191 standard non-dominated:", idx_f.size)
print("full 8191 matlab-compat non-dominated:", idx_c.size)
print("full set equals the Julia pareto_full.csv:",
      np.array_equal(idx_f + 1, np.sort(jl_full_idx)))
print("capped 4095 standard non-dominated:", idx_k.size)
print("capped set equals the recorded pareto_designs.csv:",
      np.array_equal(idx_k + 1, np.sort(rec_idx)))
print("capped Pareto designs still non-dominated in the full space:",
      int(mask_f[idx_k].sum()), "of", idx_k.size)

# ------------------------------------------------------------------
# the seven designs perfect/examples/SEILR1/robustness.bash simulated
survivors = [4234, 785, 549, 2185, 4370, 4, 512]
print()
print("design  components            row  on full frontier  on capped frontier")
for d in survivors:
    r = int(np.flatnonzero(design_ids == d)[0])
    comps = (np.flatnonzero(selection[r]) + 1).tolist()
    capped_hit = bool(mask_k[r]) if r < capped.shape[0] else False
    print(str(d).ljust(7), str(comps).ljust(22), str(r + 1).ljust(5),
          str(bool(mask_f[r])).ljust(18), capped_hit)

print()
print("survivors on the full frontier:",
      sum(bool(mask_f[int(np.flatnonzero(design_ids == d)[0])]) for d in survivors),
      "of", len(survivors))
