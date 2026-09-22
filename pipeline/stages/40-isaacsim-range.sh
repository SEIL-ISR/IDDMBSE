# PERFECT drives the contested-terrain range: eight design points (obstacle
# density 0.1 / 0.4 / 0.8 x 99th-percentile slope 15 / 25 degrees, the baseline
# point, and the terrain's authored relief), each trial one headless Isaac Sim
# process under `timeout`, 30 simulated seconds of driving.

STAGE_WHEN=range
STAGE_TITLE="Isaac Sim range campaign on PERFECT: 8 design points, one headless Isaac Sim process per trial"

stage_run() {
    local tools="$REPO/isaacsim/tools" results="$STAGE_DIR/results"

    if [ -z "${ISAACSIM_PYTHON:-}" ]; then
        skip_stage "ISAACSIM_PYTHON is not set"
        return 0
    fi
    # the range and Isaac Sim are found through these; run directories go
    # under this stage instead of isaacsim/range/doe/runs
    export IDDMBSE_RANGE_ROOT="$REPO/isaacsim" IDDMBSE_RANGE_RUNS="$STAGE_DIR/runs" ISAACSIM_PYTHON

    put "$STAGE_DIR/extra_points.json" <<'JSON'
[{"obstacle_density": 0.3, "max_slope_deg": 15.0, "friction_static": 0.6,
  "friction_dynamic": 0.5, "restitution": 0.1, "seed": 7, "duration_s": 30.0},
 {"obstacle_density": 0.1, "max_slope_deg": "authored", "friction_static": 0.6,
  "friction_dynamic": 0.5, "restitution": 0.1, "seed": 7, "duration_s": 30.0}]
JSON
    stack_up "$REPO/perfect/examples/isaacsim-range" || return 1
    # --submit loads the library, designs and environments through the Flask
    # CLI, so it runs in PERFECT's environment; the database is already new
    perfect_run python "$tools/range_campaign.py" --submit --no-reset --project-root "$STACK_PROJECT" \
        --densities 0.1,0.4,0.8 --slopes 15,25 --frictions 0.6/0.5 --restitutions 0.1 --seeds 7 \
        --duration 30 --robots "Carter v2.4" --extra "$STAGE_DIR/extra_points.json" \
        --api "$PERFECT_URL/api/v1" --timeout 2400 || return 1
    uv_python isaacsim/tools "$tools/range_campaign.py" --collect --api "$PERFECT_URL/api/v1" \
        --out "$results/campaign.csv" || return 1
    uv_python isaacsim/tools "$tools/range_campaign.py" --plot --out "$results/campaign.csv" || return 1
    veritas_args --failure-metric distance_m --failure-below 5.0
    stack_release || return 1

    [ "$DRY_RUN" = 1 ] && return 0
    local numbers
    numbers="$(python3 - "$results/campaign.csv" <<'PY'
import csv, sys
rows = list(csv.DictReader(open(sys.argv[1])))
ok = sum("SUCCESSFUL" in r["state"] for r in rows)
distance = [float(r["distance_m"]) for r in rows]
roll = [float(r["max_roll_deg"]) for r in rows]
stuck = sum(r["stuck"] in ("1", "True", "true") for r in rows)
print(len(rows), ok, round(min(distance), 2), round(max(distance), 2), round(max(roll), 1), stuck)
PY
)" || return 1
    read -r n ok dmin dmax roll stuck <<< "$numbers"
    if [ "$n" != 8 ] || [ "$ok" != 8 ]; then
        echo "expected 8 trials, all SUCCESSFUL; collected $n, SUCCESSFUL $ok"
        return 1
    fi
    headline "8 trials, 8 SUCCESSFUL; distance $dmin to $dmax m in 30 simulated s; largest roll $roll deg; stuck on $stuck"
}
