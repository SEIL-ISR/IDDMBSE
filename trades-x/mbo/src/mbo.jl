# The main script to perform Model based optimization 

# import libraries; add them to env if not present

# GR writes to an off-screen device when GKSwstype is 100, which is what lets
# the Plots calls below run without a display.
ENV["GKSwstype"] = "100"

using Random

using Statistics
using Combinatorics

using CairoMakie
using DelimitedFiles

import StatsBase
# Include the utilities scripts here


include("util_data.jl");

# Include the function scripts (Oracles) here
include("oracles.jl");

# Greedy submodular maximisation, in-repo replacement for SubmodularGreedy.jl
include("greedy_submodular.jl");

# Include scipts to implement the optimization algorithm here

# Testing space
# Datastructure to map the sensor design data
# sensors = [a1, a2, a3, a4, b1, b2, b3, b4, c1, c2, c3, d1, d2]

#----------------------------------------------
# Testing oracles
#----------------------------------------------

#= test = sensor_cost_oracle(sensors[10])
cost_oracle(design_id) =#

#= test = sensor_coverage_oracle(sensors[1])

test2 = ram_oracle(design_id, 5.0) =#
v= zeros(Bool, 13000)


#----------------------------------------------
#----------------------------------------------

p_set = collect(1:N_SENSORS)
test_obj = collect(powerset(p_set))
test_obj[344]
# Remove the nullset from the powerset
deleteat!(test_obj, 1)

# Remove the sets that violate the CARDINALITY constraint

deleteat!(test_obj, findall(x -> length(x) > 12, test_obj))


#= 
#----------------------------------------------
# object sets
p_set2 = collect(sensors)
test_obj2 = collect(powerset(p_set2))
test_obj2[344]

#---------------------------------------------- =#


data1 = zeros(length(test_obj))
data2 = zeros(length(test_obj))
data3 = zeros(length(test_obj))
data4 = zeros(length(test_obj))

#test_set_ids= Matrix{Bool}(undef, N_SENSORS, length(test_obj))

for m ∈ eachindex(test_obj)
    design_id = zeros(Bool, N_SENSORS)
    design_id[test_obj[m]] .= 1
    data1[m] = cost_oracle(design_id)
    data2[m] = ram_oracle(design_id, 5.0)
    data3[m] = power_oracle(design_id)
    data4[m] = effective_coverage_oracle(design_id)

end

metrics = hcat(data1, data2, data3, -data4)

using DataFrames
metrics_df = DataFrame(metrics, [:cost, :ram, :power, :coverage])

############## TEMPORARY ################
#### Testing te i/o pipeline


function mbo_results(sensors, C)

    n_sensors = length(sensors)
    cardinality = C
    p_set = collect(1:n_sensors)
    p_set_collect = collect(powerset(p_set))

    # Remove the nullset from the powerset
    deleteat!(p_set_collect, 1)

    # Remove the sets that violate the CARDINALITY constraint
    p_set_collect_filtered = deleteat!(p_set_collect, findall(x -> length(x) > cardinality, p_set_collect))

    # Enumerate the design id bool vectors. Initiate with undefs
    design_id_set = Matrix{Bool}(undef, N_SENSORS, length(p_set_collect_filtered))
    design_evals = zeros(length(p_set_collect_filtered),4)


    cost_col = zeros(length(p_set_collect_filtered))
    ram_col = zeros(length(p_set_collect_filtered))
    power_col = zeros(length(p_set_collect_filtered))
    coverage_col = zeros(length(p_set_collect_filtered))

    
    for m ∈ eachindex(p_set_collect_filtered)
        #Current Design id
        design_id = zeros(Bool, n_sensors)
        design_id[p_set_collect[m]] .= 1
        # Add current design to the set enum
        design_id_set[:, m] = design_id        
        cost_col[m] = cost_oracle(design_id)
        ram_col[m] = ram_oracle(design_id, 5.0)
        power_col[m] = power_oracle(design_id)
        coverage_col[m] = effective_coverage_oracle(design_id)        
    end
    design_evals = hcat(cost_col, ram_col, power_col, -coverage_col)
    
    sample_return_ind = StatsBase.sample(1:100, 5, replace=false)
    sample_return = design_id_set[:, sample_return_ind]
    return sample_return, design_evals
end

sample_return, design_evals = mbo_results(sensors, 6)

# Design eval script per design id. utilities.jl calls it, so it has to exist
# before that include runs.
function one_design_eval(design_id::Vector{Bool})
    des_dec_encoding = evalpoly(2, reverse(design_id))
    cost = cost_oracle(design_id)
    ram = ram_oracle(design_id, 5.0)
    power = power_oracle(design_id)
    coverage = effective_coverage_oracle(design_id) 
    return des_dec_encoding, cost, ram, power, coverage    
end

# Testing

include("utilities.jl");
######################################################################

"""
    mbo_smo_results(sensors, C; num_sol=3)

Greedy submodular alternative to the exhaustive enumeration in `mbo_results`.

Instead of scoring every subset, it runs `repeated_greedy` on the effective
coverage oracle at every cardinality budget k = 1..C. Coverage is the monotone
submodular metric of the four; cost, RAM and power are modular and are scored
afterwards, on the candidates greedy produced. `num_sol` rounds per budget give
a spread of distinct candidates rather than a single chain.

Returns `(design_id_set, design_evals, num_fun)`: the 13-by-m selection matrix,
the m-by-4 metric table in the `cost, RAM, power, -coverage` convention that
plot4met.csv carries, and the number of coverage-oracle calls greedy spent.
Call `pareto_rows` on `design_evals` for the approximate frontier.
"""
function mbo_smo_results(sensors, C; num_sol=3)
    n_sensors = length(sensors)
    gnd = collect(1:n_sensors)
    num_fun = 0

    candidates = Set{Int}[]
    for k in 1:C
        _, _, sols, nf, _ = repeated_greedy(gnd, coverage_gain,
                                            (e, S) -> card_add_ind(e, S, k);
                                            num_sol=num_sol, opt_size_ub=k)
        num_fun += nf
        for s in sols
            s in candidates || push!(candidates, s)
        end
    end

    m = length(candidates)
    design_id_set = zeros(Bool, n_sensors, m)
    design_evals = zeros(m, 4)
    for j in 1:m
        design_id = zeros(Bool, n_sensors)
        design_id[collect(candidates[j])] .= 1
        design_id_set[:, j] = design_id
        design_evals[j, 1] = cost_oracle(design_id)
        design_evals[j, 2] = ram_oracle(design_id, 5.0)
        design_evals[j, 3] = power_oracle(design_id)
        design_evals[j, 4] = -set_coverage(candidates[j])
    end

    return design_id_set, design_evals, num_fun
end

"""
    pareto_rows(evals)

Row indices of the non-dominated rows of `evals`, all columns minimised. Same
test as `tradesx.pareto.non_dominated`.
"""
function pareto_rows(evals)
    n = size(evals, 1)
    keep = Int[]
    for j in 1:n
        dominated = false
        for i in 1:n
            i == j && continue
            if all(evals[i, :] .<= evals[j, :]) && any(evals[i, :] .< evals[j, :])
                dominated = true
                break
            end
        end
        dominated || push!(keep, j)
    end
    return keep
end

# The greedy submodular run, reported against the exhaustive one
smo_ids, smo_evals, smo_calls = mbo_smo_results(sensors, CARDINALITY)
smo_front = pareto_rows(smo_evals)
println("greedy submodular candidates: ", size(smo_evals, 1))
println("greedy submodular approximate frontier: ", length(smo_front))
println("coverage oracle calls spent by greedy: ", smo_calls)

######################################################################
n_sensors = length(sensors)
cardinality = 6
p_set = collect(1:n_sensors)
p_set_collect = collect(powerset(p_set))

# Remove the nullset from the powerset
deleteat!(p_set_collect, 1)

# Remove the sets that violate the CARDINALITY constraint
p_set_collect_filtered = deleteat!(p_set_collect, findall(x -> length(x) > cardinality, p_set_collect))

# Enumerate the design id bool vectors. Initiate with undefs
design_id_set = Matrix{Bool}(undef, N_SENSORS, length(p_set_collect_filtered))
design_evals = zeros(length(p_set_collect_filtered), 4)


cost_col = zeros(length(p_set_collect_filtered))
ram_col = zeros(length(p_set_collect_filtered))
power_col = zeros(length(p_set_collect_filtered))
coverage_col = zeros(length(p_set_collect_filtered))

for m ∈ eachindex(p_set_collect_filtered)
    #Current Design id
    design_id = zeros(Bool, n_sensors)
    design_id[p_set_collect[m]] .= 1
    # Add current design to the set enum
    design_id_set[:, m] = design_id
    cost_col[m] = cost_oracle(design_id)
    ram_col[m] = ram_oracle(design_id, 5.0)
    power_col[m] = power_oracle(design_id)
    coverage_col[m] = effective_coverage_oracle(design_id)
end
design_evals = hcat(cost_col, ram_col, power_col, -coverage_col)
unsigned_design_evals = hcat(cost_col, ram_col, power_col, coverage_col)

minimum(cost_col)
maximum(cost_col)
minimum(ram_col)
maximum(ram_col)

minimum(power_col)
maximum(power_col)


minimum(coverage_col)
maximum(coverage_col)
mean(coverage_col) 

using Plots

p1 = Plots.scatter(cost_col, coverage_col / (maximum(coverage_col) - minimum(coverage_col)), markersize=1, color=:blue, xlabel="Cost", title="(Normalized) Coverage vs Cost[\$]", legend=false)
p2 = Plots.scatter(ram_col, coverage_col / (maximum(coverage_col) - minimum(coverage_col)), markersize=1, color=:blue, xlabel="RAM", title="RAM [Mb] vs (Normalized) Coverage", legend=false)
p3 = Plots.scatter(power_col, coverage_col / (maximum(coverage_col) - minimum(coverage_col)), markersize=1, color=:blue, xlabel="Power", title="Power[watts] vs (Normalized) Coverage", legend=false)

p5 = Plots.plot(p1, p2, p3, layout=(3, 1), title="Coverage vs Cost")

l = @layout [a; b c]
p6= Plots.plot(p1, p2, p3, layout=l)



# sens_fd.jl includes util_data_mod.jl, which redefines the four sensor structs
# with `Real` fields so ForwardDiff can push dual numbers through them. Loading
# it into Main would clash with the structs util_data.jl already defined here,
# so it gets its own module.
module SensFD
include("sens_fd.jl")
end

#= 
r_cost = LinRange(minimum(cost_col), maximum(cost_col), 4)
r_power = LinRange(minimum(power_col), maximum(power_col), 4)
r_ram = LinRange(minimum(ram_col), maximum(ram_col), 4)
#----------------------------------------------

greedy_design = zeros(Bool, N_SENSORS) =#
#----------------------------------------------

# Design eval script per design id


des_id, des_cost, des_ram, des_pow, des_cov = one_design_eval(vec(Bool[0 0 0 0 0 0 0 0 0 0 1 0 0]))

#--------------------------------------------
