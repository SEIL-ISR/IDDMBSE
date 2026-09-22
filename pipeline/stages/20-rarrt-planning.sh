# The risk-sensitive planner study as a PERFECT campaign: the five RA-RRT*
# policies as one component's implementations, 3 rock fields x 4 noise levels
# x 5 seeds as environments, one trial each.

STAGE_WHEN=all
STAGE_TITLE="risk-sensitive planner campaign: 5 policies x 60 environments on PERFECT"

stage_run() {
    local case_study="case-studies/A2-risk-sensitive-planning"
    local driver="$REPO/$case_study/run_perfect_campaign.py"
    local results="$STAGE_DIR/results"

    # the planner is numpy and scipy, which PERFECT's own environment does not
    # carry; one thread per trial, the runner takes them one at a time
    export RARRT_PYTHON="$TRIAL_PYTHON" RARRT_PACKAGE="$REPO/$case_study" OMP_NUM_THREADS=1
    stack_up "$REPO/perfect/examples/rarrt-planning" || return 1
    uv_python "$case_study" "$driver" --submit --url "$PERFECT_URL" --wait 2400 || return 1
    uv_python "$case_study" "$driver" --collect --url "$PERFECT_URL" --out "$results" || return 1
    veritas_args --metric hazard_rate --failure-metric over_budget --failure-above 0.0 --group-by design
    stack_release || return 1

    [ "$DRY_RUN" = 1 ] && return 0
    expect_trials 300 || return 1
    # cells.csv: env, sigma, policy, alpha, runs, success_rate, failure_rate, ...
    local hard
    hard="$(awk -F, '$1 == "hard" && $2 == "0.5" && ($3 == "rrtstar" || $3 == "cvar0.9") { printf "%s%s %.4f", sep, $3, $7; sep = ", " }' "$results/cells.csv")"
    headline "300 trials, 300 SUCCESSFUL; planner found a path in $(log_number "planner found a path in ") of 300;" \
        "failure rate in the hard field at sigma 0.5: $hard"
}
