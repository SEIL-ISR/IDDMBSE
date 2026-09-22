# The conformal-perception calibration data as a PERFECT campaign: three
# detector configurations x 3 clutter bands x 30 seeds, one closed-loop episode
# per trial, then split conformal calibration on what the trials wrote back.

STAGE_WHEN=all
STAGE_TITLE="conformal-calibration campaign: 3 detectors x 90 environments on PERFECT, split conformal calibration"

stage_run() {
    local case_study="case-studies/B2-conformal-perception"
    local driver="$REPO/$case_study/run_perfect_campaign.py"
    local results="$STAGE_DIR/results"

    # the closed loop is numpy, which PERFECT's own environment does not carry;
    # one thread per trial, the runner takes them one at a time
    export CPNAV_PYTHON="$TRIAL_PYTHON" CPNAV_PACKAGE="$REPO/$case_study" OMP_NUM_THREADS=1
    stack_up "$REPO/perfect/examples/conformal-calibration" || return 1
    uv_python "$case_study" "$driver" --submit --url "$PERFECT_URL" --wait 2400 || return 1
    uv_python "$case_study" "$driver" --collect --url "$PERFECT_URL" --out "$results" || return 1
    veritas_args --metric coverage_margin --failure-metric collisions --failure-above 0.0 --group-by design
    stack_release || return 1

    [ "$DRY_RUN" = 1 ] && return 0
    expect_trials 270 || return 1
    # coverage.csv: alpha, target_coverage, q, calibration_rows, holdout_rows, holdout_coverage, ...
    local coverage
    coverage="$(awk -F, '$1 == "0.1" { printf "held-out coverage %.4f at alpha 0.1 (q %.3f m, calibrated on %d detections)", $6, $3, $4 }' "$results/coverage.csv")"
    headline "270 trials, 270 SUCCESSFUL; $(log_number "episodes: [0-9]* detections: ") detections; $coverage"
}
