using FiniteDifferences

using ForwardDiff
using Random

using Statistics
using Combinatorics

using CairoMakie
using DelimitedFiles

import StatsBase

include("util_data_mod.jl");

# Include the function scripts (Oracles) here
include("oracles.jl");

# Include scipts to implement the optimization algorithm here

# Testing space
# Datastructure to map the sensor design data
sensors = [a1, a2, a3, a4, b1, b2, b3, b4, c1, c2, c3, d1, d2]

#----------------------------------------------
# Testing oracles
#----------------------------------------------

test = sensor_coverage_oracle(sensors[10])

FiniteDifferences.forward_fdm(sensor_coverage_oracle, sensors[10])
#= test = sensor_coverage_oracle(sensors[1])

test2 = ram_oracle(design_id, 5.0) =#
v = zeros(Bool, 13000)


#----------------------------------------------
#----------------------------------------------

p_set = collect(1:N_SENSORS)
test_obj = collect(powerset(p_set))
test_obj[344]
# Remove the nullset from the powerset
deleteat!(test_obj, 1)

# Remove the sets that violate the CARDINALITY constraint

deleteat!(test_obj, findall(x -> length(x) > 12, test_obj))


