# Headless entry point for the model-based optimization stage.
#
#   julia --project=. run_mbo.jl [cardinality] [out.csv] [reference.csv]
#
# Enumerates every non-empty sensor subset up to the cardinality limit, scores
# it with the oracles in src/oracles.jl, and writes one row per design as
# cost, RAM, power, -coverage. Coverage is stored negated so that all four
# columns are minimised, which is the convention plot4met.csv carries.
#
# src/mbo.jl is the original exploratory script: same enumeration, plus
# plotting through GLMakie/Plots and the sensitivity experiments. This script
# runs the enumeration only, so it needs no display.

using Combinatorics
using DelimitedFiles

include("src/util_data.jl")
include("src/oracles.jl")

cardinality = length(ARGS) >= 1 ? parse(Int, ARGS[1]) : CARDINALITY
outfile = length(ARGS) >= 2 ? ARGS[2] : "mbo_design_evals.csv"

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

# Pareto set size, same standard non-dominance test as tradesx.pareto
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
println("Pareto set size: $(count(.!dominated))")

if length(ARGS) >= 3
    ref = readdlm(ARGS[3], ',', Float64)
    println("reference rows: $(size(ref, 1))")
    if size(ref) == size(evals)
        println("max abs difference vs reference: $(maximum(abs.(evals .- ref)))")
    else
        println("shape mismatch, no comparison")
    end
end
