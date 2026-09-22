# Greedy maximisation of a monotone submodular function under a cardinality
# constraint. This replaces the `SubmodularGreedy.jl` dependency, which does not
# load on Julia 1.12 (it reaches for `Core.TypeName.mt`, removed in 1.12) and is
# unmaintained upstream (github.com/crharshaw/SubmodularGreedy.jl).
#
# The two oracle arguments keep the upstream calling convention:
#   f_diff(elm, sol)           -> marginal gain f(sol + elm) - f(sol)
#   ind_add_oracle(elm, sol)   -> true when sol + elm is still feasible
#
# Differences from upstream, all deliberate:
#   - `greedy` here is the plain (non-lazy) greedy. Upstream keeps a priority
#     queue and skips stale entries; with 13 ground-set elements the queue buys
#     nothing and the plain loop is easier to read.
#   - upstream returns a fifth value `knap_reject`. There are no knapsack
#     constraints here, so it is not returned.
#   - only `greedy`, `repeated_greedy` and `card_add_ind` are provided; the
#     sample-greedy and simultaneous-greedy variants are not used anywhere in
#     this package.

"""
    card_add_ind(elm, sol, k)

Independence oracle for a cardinality-`k` constraint: can `elm` join `sol`?
"""
function card_add_ind(elm::Integer, sol::Set{<:Integer}, k::Integer)
    return length(union(sol, elm)) <= k
end

"""
    greedy(gnd, f_diff, ind_add_oracle; opt_size_ub)

Greedy maximisation. Repeatedly adds the feasible element of largest positive
marginal gain until nothing feasible improves the objective.

Returns `(sol, f_val, num_fun, num_oracle)`: the solution set, its objective
value (the sum of the accepted gains, so `f(empty set)` is taken as 0), the
number of marginal-gain evaluations and the number of independence queries.

For a monotone submodular `f` and a cardinality constraint this is the classic
(1 - 1/e) approximation.
"""
function greedy(gnd::AbstractVector{<:Integer}, f_diff, ind_add_oracle;
                opt_size_ub::Integer=length(gnd))
    sol = Set{Int}()
    f_val = 0.0
    num_fun = 0
    num_oracle = 0

    while length(sol) < opt_size_ub
        best_elm = 0
        best_gain = 0.0
        for e in gnd
            e in sol && continue
            num_oracle += 1
            ind_add_oracle(e, sol) || continue
            num_fun += 1
            g = f_diff(e, sol)
            if g > best_gain
                best_gain = g
                best_elm = e
            end
        end
        best_elm == 0 && break
        push!(sol, best_elm)
        f_val += best_gain
    end

    return sol, f_val, num_fun, num_oracle
end

"""
    repeated_greedy(gnd, f_diff, ind_add_oracle; num_sol, opt_size_ub)

Runs `greedy` `num_sol` times, removing the elements of each solution from the
ground set before the next round. Returns
`(best_sol, best_f_val, sols, num_fun, num_oracle)` where `sols` is the list of
all rounds' solutions, best first in the order they were found.

The rounds after the first are the reason this exists: they give a spread of
distinct candidate designs rather than one, which is what the trade-off study
needs.
"""
function repeated_greedy(gnd::AbstractVector{<:Integer}, f_diff, ind_add_oracle;
                         num_sol::Integer=3, opt_size_ub::Integer=length(gnd))
    remaining = collect(Int, gnd)
    sols = Set{Int}[]
    best_sol = Set{Int}()
    best_f_val = -Inf
    num_fun = 0
    num_oracle = 0

    for _ in 1:num_sol
        isempty(remaining) && break
        sol, f_val, nf, no = greedy(remaining, f_diff, ind_add_oracle;
                                    opt_size_ub=opt_size_ub)
        num_fun += nf
        num_oracle += no
        isempty(sol) && break
        push!(sols, sol)
        if f_val > best_f_val
            best_sol = sol
            best_f_val = f_val
        end
        setdiff!(remaining, sol)
    end

    return best_sol, best_f_val, sols, num_fun, num_oracle
end

# ------------------------------------------------------------------
# marginal-gain oracle over the sensor catalogue

"""
    set_coverage(slots)

Effective coverage of the sensor set `slots` (1-based catalogue indices).

`effective_coverage_oracle` mutates the global `sensors` array as it merges
ranges and fields of view, so calling it twice on the same design gives
different answers. Greedy calls it thousands of times, so this wrapper saves and
restores the catalogue around every call. The value returned for a given set is
therefore the value the recorded enumeration would have produced with a fresh
catalogue.
"""
function set_coverage(slots)
    saved = deepcopy(sensors)
    d = zeros(Bool, N_SENSORS)
    for s in slots
        d[s] = true
    end
    v = effective_coverage_oracle(d)
    for i in eachindex(sensors)
        sensors[i] = saved[i]
    end
    return v
end

"""
    coverage_gain(elm, sol)

Marginal gain in effective coverage from adding catalogue slot `elm` to `sol`.
"""
function coverage_gain(elm::Integer, sol::Set{<:Integer})
    elm in sol && return 0.0
    return set_coverage(union(sol, elm)) - set_coverage(sol)
end
