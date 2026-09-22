# VERITAS's model-based module: the SysML battery state machine and the
# example behavior tree written as UPPAAL networks of timed automata, then
# checked by verifyta when UPPAAL is installed (UPPAAL_HOME, or verifyta on
# the PATH).

STAGE_WHEN=default
STAGE_TITLE="UPPAAL: write the SysML battery model and the behavior-tree model, check both with verifyta"

stage_run() {
    local battery="$STAGE_DIR/battery_sm.xml" bt="$STAGE_DIR/BT_converted.xml" verifyta

    uv_python veritas "$REPO/pipeline/lib/battery_model.py" "$battery" || return 1
    uv_python veritas "$REPO/veritas/formal/bt2automata/demo.py" "$bt" || return 1

    if ! verifyta="$(find_verifyta)"; then
        skip_stage "verifyta not found (set UPPAAL_HOME); both models written, not checked"
        return 0
    fi
    uv_python veritas "$REPO/veritas/formal/verify.py" "$battery" "$bt" --verifyta "$verifyta" \
        --out "$STAGE_DIR" || return 1

    [ "$DRY_RUN" = 1 ] && return 0
    headline "$(python3 - "$STAGE_DIR/verification_report.json" <<'PY'
import collections, json, os, sys
report = json.load(open(sys.argv[1]))
parts = []
for m in report["models"]:
    verdicts = collections.Counter(q["verdict"] for q in m["queries"])
    parts.append(os.path.basename(m["model"]) + ": " + str(sum(verdicts.values())) + " queries, "
                 + ", ".join(str(n) + " " + v for v, n in sorted(verdicts.items())))
print(report["version"] + "; " + "; ".join(parts))
PY
)"
}
