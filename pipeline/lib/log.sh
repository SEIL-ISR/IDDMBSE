# Helpers shared by pipeline/run.sh and the stages: how a command is shown and
# run, how a stage leaves its headline, and a few lookups.
#
# Sourced, never run. run.sh sets REPO, RUN_DIR and DRY_RUN; the stage runner
# sets STAGE_NAME and STAGE_DIR before a stage's stage_run is called.

rel() {
    # a path inside the repository, relative to it; anything else as it is
    printf '%s\n' "${1#"$REPO"/}"
}

show() {
    # print a command the way it will run, with repository paths made relative
    local a shown=()
    for a in "$@"; do
        shown+=("${a//"$REPO"\//}")
    done
    printf '+'
    printf ' %q' "${shown[@]}"
    printf '\n'
}

step() {
    # show a command, then run it unless this is a dry run; its output also
    # goes to the stage log, which the stage reads its numbers back from
    show "$@"
    [ "$DRY_RUN" = 1 ] && return 0
    "$@" 2>&1 | tee -a "$STAGE_DIR/stage.log"
    return "${PIPESTATUS[0]}"
}

uv_python() {
    # uv_python <tool directory> <args...>: python in that tool's own uv environment
    local project="$1"
    shift
    step uv run --frozen --project "$REPO/$project" python "$@"
}

put() {
    # put <file>: write stdin to the file, or on a dry run say it would
    if [ "$DRY_RUN" = 1 ]; then
        echo "+ write $(rel "$1")"
        cat > /dev/null
        return 0
    fi
    mkdir -p "$(dirname "$1")"
    cat > "$1"
}

headline() {
    # the one line of numbers this stage contributes to SUMMARY.md
    echo "headline: $*"
    [ "$DRY_RUN" = 1 ] || printf '%s\n' "$*" > "$STAGE_DIR/headline.txt"
}

skip_stage() {
    echo "skipped: $*"
    [ "$DRY_RUN" = 1 ] && return 0
    printf 'skipped: %s\n' "$*" > "$STAGE_DIR/headline.txt"
    : > "$STAGE_DIR/skipped"
}

selected() {
    # is this stage part of the run (run.sh exports SELECTED)
    [[ " $SELECTED " == *" $1 "* ]]
}

log_number() {
    # log_number <prefix>: the number printed right after <prefix> in the stage
    # log, the last time it was printed
    sed -n "s/^$1\([0-9][0-9]*\).*/\1/p" "$STAGE_DIR/stage.log" | tail -1
}

expect_trials() {
    # expect_trials <n>: the campaign driver collected n trials and all of them
    # reached SUCCESSFUL
    local collected successful
    collected=$(log_number "trials collected: ")
    successful=$(log_number "SUCCESSFUL trials: ")
    if [ "$collected" != "$1" ] || [ "$successful" != "$1" ]; then
        echo "expected $1 trials, all SUCCESSFUL; collected ${collected:-none}, SUCCESSFUL ${successful:-none}"
        return 1
    fi
}

veritas_args() {
    # the arguments VERITAS's failure-rate report takes for this campaign's
    # database; the veritas-report stage reads them back
    if [ "$DRY_RUN" = 1 ]; then
        echo "+ write $(rel "$STAGE_DIR/veritas.args"): $*"
        return 0
    fi
    printf '%s\n' "$@" > "$STAGE_DIR/veritas.args"
}

find_verifyta() {
    # the same search formal/verify.py makes: UPPAAL 4.1's layout, 5.x's, then PATH
    local v
    for v in "${UPPAAL_HOME:+$UPPAAL_HOME/bin-Linux/verifyta}" \
             "${UPPAAL_HOME:+$UPPAAL_HOME/bin/verifyta}" \
             "$(command -v verifyta 2>/dev/null)"; do
        if [ -n "$v" ] && [ -x "$v" ]; then
            echo "$v"
            return 0
        fi
    done
    return 1
}

seconds_since() {
    # wall seconds since an $EPOCHREALTIME stamp, to a tenth
    awk -v a="$1" -v b="$EPOCHREALTIME" 'BEGIN { printf "%.1f", b - a }'
}
