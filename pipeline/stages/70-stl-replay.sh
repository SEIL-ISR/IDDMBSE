# VERITAS's runtime module: the STL observer replayed over the range
# trajectories shipped in isaacsim/results/trajectories against the range
# safety obligations (roll, pitch, progress), and over this run's own range
# trajectories when --range ran.

STAGE_WHEN=default
STAGE_TITLE="STL observer replayed over the range trajectories"

stage_run() {
    local replay="$REPO/veritas/runtime/stl-observer/replay_observer.py"
    local spec="$REPO/veritas/runtime/stl-observer/specs/range_safety.yaml"
    local shipped="$REPO/isaacsim/results" fresh="$RUN_DIR/isaacsim-range/results"

    uv_python veritas "$replay" "$shipped"/trajectories/trial_*.csv --spec "$spec" \
        --points "$shipped/campaign.csv" --point-columns environment --out "$STAGE_DIR/shipped" || return 1
    local outs=("$STAGE_DIR/shipped")
    # this run's own trajectories, when the range stage ran
    if { [ "$DRY_RUN" = 1 ] && selected isaacsim-range && [ -n "${ISAACSIM_PYTHON:-}" ]; } \
        || compgen -G "$fresh/trajectories/trial_*.csv" > /dev/null; then
        uv_python veritas "$replay" "$fresh"/trajectories/trial_*.csv --spec "$spec" \
            --points "$fresh/campaign.csv" --point-columns environment --out "$STAGE_DIR/this-run" || return 1
        outs+=("$STAGE_DIR/this-run")
    fi

    [ "$DRY_RUN" = 1 ] && return 0
    headline "$(python3 - "${outs[@]}" <<'PY'
import csv, os, sys
parts = []
for out in sys.argv[1:]:
    rows = list(csv.DictReader(open(os.path.join(out, "verdicts.csv"))))
    names = [c[:-len("_verdict")] for c in rows[0] if c.endswith("_verdict")]
    broken = ", ".join(n + " " + str(sum(r[n + "_verdict"] == "violated" for r in rows)) for n in names)
    parts.append(os.path.basename(out) + " trajectories: " + str(len(rows)) + " traces, violated " + broken)
print("; ".join(parts))
PY
)"
}
