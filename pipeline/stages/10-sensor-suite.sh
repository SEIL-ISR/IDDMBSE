# TRADES-X's data-driven stage against PERFECT: ten sensor-suite designs over
# eighteen scenarios of the sensor-suite-sim example, one trial each, collected
# from PERFECT's trial table and ranked by the MAVF.

STAGE_WHEN=default
STAGE_TITLE="sensor-suite campaign through TRADES-X: 10 designs x 18 scenarios on PERFECT, MAVF ranking"

stage_run() {
    local driver="$REPO/trades-x/case-studies/sensor-suite/run_ddo_campaign.py"
    local results="$STAGE_DIR/results"

    # the simulation is numpy, which PERFECT's own environment does not carry
    export SENSOR_SIM_PYTHON="$TRIAL_PYTHON"
    stack_up "$REPO/perfect/examples/sensor-suite-sim" || return 1
    uv_python trades-x "$driver" --submit --url "$PERFECT_URL" --wait 1800 || return 1
    uv_python trades-x "$driver" --collect --url "$PERFECT_URL" --out "$results" || return 1
    veritas_args --tag ddo --group-by design --failure-metric success_rate --failure-below 1.0
    stack_release || return 1

    [ "$DRY_RUN" = 1 ] && return 0
    expect_trials 180 || return 1
    # mavf_ddo_ranking.csv is in rank order: design, mavf_rank, mavf_score, ...
    local first last
    first="$(awk -F, 'NR == 2 { printf "%s (%.4f)", $1, $3 }' "$results/mavf_ddo_ranking.csv")"
    last="$(awk -F, 'END { printf "%s (%.4f)", $1, $3 }' "$results/mavf_ddo_ranking.csv")"
    headline "180 trials, 180 SUCCESSFUL; MAVF first $first, last $last"
}
