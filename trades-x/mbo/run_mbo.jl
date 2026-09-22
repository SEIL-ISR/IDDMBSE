# Headless entry point for the model-based optimization stage.
#
#   julia --project=. run_mbo.jl [cardinality] [out.csv] [reference.csv] [pareto.csv]
#
# Enumerates every non-empty sensor subset up to the cardinality limit, scores
# it with the oracles in src/oracles.jl, and writes one row per design as
# cost, RAM, power, -coverage. Coverage is stored negated so that all four
# columns are minimised, which is the convention plot4met.csv carries.
#
# Defaults are CARDINALITY (6) and mbo_design_evals.csv. Pass "-" for
# reference.csv to skip the comparison but still write the Pareto indices.
# With cardinality 13 there is no cap, so the enumeration is the full
# 2^13 - 1 = 8191 non-empty subsets.
#
# It also runs the greedy submodular search over the same design space and
# reports how large an approximate frontier that produces, for the same
# oracles, at a small fraction of the oracle calls.
#
# src/mbo.jl is the original exploratory script: same enumeration, plus the
# scatter plots, the animations and the sensitivity experiments. This script
# runs the enumeration only.

using Combinatorics
using DelimitedFiles

include("src/util_data.jl")
include("src/oracles.jl")
include("src/greedy_submodular.jl")

# effective_coverage_oracle mutates the catalogue as it merges ranges and fields
# of view, so keep a pristine copy to restore before the greedy run.
fresh_sensors = deepcopy(sensors)

cardinality = length(ARGS) >= 1 ? parse(Int, ARGS[1]) : CARDINALITY
outfile = length(ARGS) >= 2 ? ARGS[2] : "mbo_design_evals.csv"
reffile = length(ARGS) >= 3 && ARGS[3] != "-" ? ARGS[3] : nothing
paretofile = length(ARGS) >= 4 ? ARGS[4] : nothing

subsets = collect(powerset(1:N_SENSORS, 1, cardinality))
println("sensors: $N_SENSORS")
println("cardinality: $cardinality")
println("designs enumerated: $(length(subsets))")

evals = zeros(length(subsets), 4)
for m in eachindex(subsets)
    d = zeros(Bool, N_SENSORS)
    d[subsets[m]] .= 1
    evals[m, 1] = cost_oracle(d)
    evals[m, 2] = ram_oracle(d, 5.0)
    evals[m, 3] = power_oracle(d)
    evals[m, 4] = -effective_coverage_oracle(d)
end

writedlm(outfile, evals, ',')
println("wrote $outfile")

# Pareto set, same standard non-dominance test as tradesx.pareto
n = size(evals, 1)
dominated = falses(n)
for j in 1:n
    for i in 1:n
        if i != j
            ge = true
            gt = false
            for k in 1:4
                ge &= evals[i, k] <= evals[j, k]
                gt |= evals[i, k] < evals[j, k]
            end
            if ge && gt
                dominated[j] = true
                break
            end
        end
    end
end
pareto_idx = findall(.!dominated)
println("Pareto set size: $(length(pareto_idx))")

if paretofile !== nothing
    writedlm(paretofile, pareto_idx, ',')
    println("wrote $paretofile")
end

# Greedy submodular search over the same space. The enumeration above has left
# the sensor catalogue mutated, so restore it before the greedy run;
# set_coverage then keeps it pristine around every call.
for i in eachindex(sensors)
    sensors[i] = fresh_sensors[i]
end

gnd = collect(1:N_SENSORS)
greedy_sets = Set{Int}[]
greedy_calls = 0
for k in 1:cardinality
    _, _, sols, nf, _ = repeated_greedy(gnd, coverage_gain, (e, S) -> card_add_ind(e, S, k);
                                        num_sol=3, opt_size_ub=k)
    global greedy_calls += nf
    for s in sols
        s in greedy_sets || push!(greedy_sets, s)
    end
end

g = length(greedy_sets)
gevals = zeros(g, 4)
for j in 1:g
    d = zeros(Bool, N_SENSORS)
    d[collect(greedy_sets[j])] .= 1
    gevals[j, 1] = cost_oracle(d)
    gevals[j, 2] = ram_oracle(d, 5.0)
    gevals[j, 3] = power_oracle(d)
    gevals[j, 4] = -set_coverage(greedy_sets[j])
end

gdom = falses(g)
for j in 1:g
    for i in 1:g
        if i != j && all(gevals[i, :] .<= gevals[j, :]) && any(gevals[i, :] .< gevals[j, :])
            gdom[j] = true
            break
        end
    end
end
println("greedy submodular candidates: $g")
println("greedy submodular approximate frontier: $(count(.!gdom))")
println("coverage oracle calls spent by greedy: $greedy_calls")

if reffile !== nothing
    ref = readdlm(reffile, ',', Float64)
    println("reference rows: $(size(ref, 1))")
    if size(ref, 1) <= size(evals, 1)
        rows = size(ref, 1)
        println("max abs difference vs reference over its $rows rows: $(maximum(abs.(evals[1:rows, :] .- ref)))")
    else
        println("reference has more rows than this run, no comparison")
    end
end
