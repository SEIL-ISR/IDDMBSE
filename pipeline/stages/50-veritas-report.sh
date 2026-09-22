# VERITAS's data-driven module over every campaign database this run wrote:
# failure rates with exact and Wilson intervals, per design. Each campaign stage
# leaves the report's arguments in <run>/<stage>/veritas.args; its database is
# <run>/<stage>/project/project.db.

STAGE_WHEN=default
STAGE_TITLE="VERITAS failure-rate report over each campaign database of the run"

stage_run() {
    local report="$REPO/veritas/datadriven/report.py" args_file campaign args line seen summary=""

    if [ "$DRY_RUN" = 1 ]; then
        echo "+ for each campaign stage that wrote veritas.args, from its project directory:"
        echo "+ uv run --frozen --project veritas python $(rel "$report") --db project.db" \
            "--out $(rel "$STAGE_DIR")/<campaign> <the arguments in veritas.args>"
        return 0
    fi

    for args_file in "$RUN_DIR"/*/veritas.args; do
        [ -f "$args_file" ] || continue
        campaign="$(basename "$(dirname "$args_file")")"
        mapfile -t args < "$args_file"
        seen="$(cat "$STAGE_DIR/stage.log" 2> /dev/null | wc -l)"
        # run from the project directory so that report.json names the
        # database by its file name only
        ( cd "$RUN_DIR/$campaign/project" \
            && uv_python veritas "$report" --db project.db --out "$STAGE_DIR/$campaign" "${args[@]}" ) \
            || return 1
        line="$(tail -n +"$((seen + 1))" "$STAGE_DIR/stage.log" | grep "^outcome from " | tail -1)"
        summary+="${summary:+; }$campaign: ${line#outcome from }"
    done
    if [ -z "$summary" ]; then
        echo "no campaign database in this run"
        return 1
    fi
    headline "$summary"
}
