#!/usr/bin/env bash
# One command for the tool chain: a private PERFECT stack, the sensor-suite
# campaign through TRADES-X, VERITAS's failure-rate report over its database,
# UPPAAL on the models VERITAS writes, the STL observer over the range
# trajectories, and a summary.
#
#   pipeline/run.sh [--all] [--range] [--keep-stack] [--out <dir>]
#   pipeline/run.sh --list
#   pipeline/run.sh --dry-run [--all] [--range]
#
#   --all         add the risk-sensitive planner and conformal-calibration campaigns
#   --range       add the Isaac Sim range campaign (skipped if ISAACSIM_PYTHON is unset)
#   --list        list the stages and stop
#   --dry-run     print the stages the run would make and their commands; start nothing
#   --keep-stack  leave the last campaign's PERFECT stack up after a run that succeeds
#   --out <dir>   the run directory (default pipeline/out/<date>-<time>)
#
# Environment: PIPELINE_REDIS_PORT, PIPELINE_FLASK_PORT, PIPELINE_RUNNER_PORT
# (6390, 5001, 8003); PIPELINE_TRIAL_PYTHON, the interpreter the ROS-free
# examples run their trials with (/usr/bin/python3; it needs numpy, scipy and
# PyYAML); UPPAAL_HOME (optional); ISAACSIM_PYTHON (optional, for --range);
# PIPELINE_STAGES, a directory of stage files to run instead of pipeline/stages.
#
# Each stage is a file pipeline/stages/NN-<name>.sh, run in number order, and
# writes under <run>/<name>/. Whatever a run starts is stopped when it ends,
# on failure and on Ctrl-C too.

set -u

PIPELINE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(dirname "$PIPELINE")"
LIB="$PIPELINE/lib"
STAGES="${PIPELINE_STAGES:-$PIPELINE/stages}"

REDIS_PORT="${PIPELINE_REDIS_PORT:-6390}"
FLASK_PORT="${PIPELINE_FLASK_PORT:-5001}"
RUNNER_PORT="${PIPELINE_RUNNER_PORT:-8003}"
TRIAL_PYTHON="${PIPELINE_TRIAL_PYTHON:-/usr/bin/python3}"

ALL=0
RANGE=0
LIST=0
DRY_RUN=0
KEEP_STACK=0
OUT=""
ARGS="$*"

while [ $# -gt 0 ]; do
    case "$1" in
        --all) ALL=1; shift ;;
        --range) RANGE=1; shift ;;
        --list) LIST=1; shift ;;
        --dry-run) DRY_RUN=1; shift ;;
        --keep-stack) KEEP_STACK=1; shift ;;
        --out) OUT="${2:?--out needs a directory}"; shift 2 ;;
        -h|--help) awk 'NR > 1 && !/^#/ { exit } NR > 1 { sub(/^# ?/, ""); print }' "${BASH_SOURCE[0]}"; exit 0 ;;
        *) echo "unknown argument $1 (see --help)"; exit 2 ;;
    esac
done

# A sourced ROS 2 environment puts its site-packages on PYTHONPATH, and it must
# not reach the tools' own environments; neither must an activated virtual
# environment. Unbuffered output lets a campaign's progress reach the log as it
# happens.
unset PYTHONPATH VIRTUAL_ENV
export PYTHONUNBUFFERED=1

RUN_ID="$(date +%Y%m%d-%H%M%S)"
if [ -n "$OUT" ]; then
    RUN_DIR="$(realpath -m "$OUT")"
    RUN_ID="$(basename "$RUN_DIR")"
else
    RUN_DIR="$REPO/pipeline/out/$RUN_ID"
fi

# shellcheck source=lib/log.sh
source "$LIB/log.sh"
# shellcheck source=lib/stack.sh
source "$LIB/stack.sh"

stage_name() {
    local base
    base="$(basename "$1" .sh)"
    echo "${base#[0-9][0-9]-}"
}

stage_field() {
    # stage_field <file> <variable>: a stage's declared STAGE_WHEN or STAGE_TITLE
    ( source "$1"; eval "echo \"\${$2:-}\"" )
}

wanted() {
    case "$(stage_field "$1" STAGE_WHEN)" in
        default) return 0 ;;
        all) [ "$ALL" = 1 ] ;;
        range) [ "$RANGE" = 1 ] ;;
        *) return 1 ;;
    esac
}

FILES=()
for f in "$STAGES"/[0-9][0-9]-*.sh; do
    [ -f "$f" ] && FILES+=("$f")
done

if [ "$LIST" = 1 ]; then
    for f in "${FILES[@]}"; do
        when="$(stage_field "$f" STAGE_WHEN)"
        case "$when" in all) when="--all" ;; range) when="--range" ;; esac
        echo "$(basename "$f" .sh) [$when] $(stage_field "$f" STAGE_TITLE)"
    done
    echo "summary [always] write SUMMARY.md: each stage's status, wall seconds, headline numbers and output"
    echo "teardown [always] stop every process the run started, also on failure"
    exit 0
fi

RUN=()
for f in "${FILES[@]}"; do
    wanted "$f" && RUN+=("$f")
done
SELECTED=""
for f in "${RUN[@]}"; do
    SELECTED+="$(stage_name "$f") "
done
export SELECTED ALL RANGE

if [ "$DRY_RUN" = 1 ]; then
    echo "dry run: nothing is started and nothing is written"
    echo "run directory $(rel "$RUN_DIR"); PERFECT stack on Redis $REDIS_PORT, Flask $FLASK_PORT, runner $RUNNER_PORT"
    for f in "${RUN[@]}"; do
        STAGE_NAME="$(stage_name "$f")"
        STAGE_DIR="$RUN_DIR/$STAGE_NAME"
        echo
        echo "== $STAGE_NAME: $(stage_field "$f" STAGE_TITLE)"
        ( source "$f"; stage_run ) || exit 1
    done
    echo
    echo "== summary"
    echo "+ write $(rel "$RUN_DIR")/SUMMARY.md"
    echo
    echo "== teardown"
    echo "+ stop the processes in $(rel "$RUN_DIR")/stack.pids and every process below them"
    exit 0
fi

# ------------------------------------------------------------------
# a real run

if ! ports_free; then
    echo "refusing to start: set PIPELINE_REDIS_PORT, PIPELINE_FLASK_PORT or PIPELINE_RUNNER_PORT to free ports"
    exit 1
fi
if [ -d "$RUN_DIR" ] && [ -n "$(ls -A "$RUN_DIR")" ]; then
    echo "refusing to start: $(rel "$RUN_DIR") exists and is not empty"
    exit 1
fi
mkdir -p "$RUN_DIR"
: > "$STACK_PIDS"
: > "$RUN_DIR/stack-history.txt"

START="$EPOCHREALTIME"
START_TEXT="$(date '+%Y-%m-%d %H:%M:%S %Z')"
NAMES=()
STATUS=()
WALL=()
STAGE_PID=""
STAGE_T0="$START"

write_summary() {
    local code="$1" i name headline commit=""
    if git -C "$REPO" rev-parse --short HEAD > /dev/null 2>&1; then
        commit="$(git -C "$REPO" rev-parse --short HEAD)"
        [ -n "$(git -C "$REPO" status --porcelain 2> /dev/null)" ] && commit+=" with local changes"
    fi
    {
        echo "# Pipeline run $RUN_ID"
        echo
        echo "- command: \`pipeline/run.sh${ARGS:+ $ARGS}\`"
        [ -n "$commit" ] && echo "- commit: $commit"
        echo "- started $START_TEXT; $(seconds_since "$START") s in all; exit $code"
        echo "- PERFECT stack ports: Redis $REDIS_PORT, Flask $FLASK_PORT, runner $RUNNER_PORT"
        echo
        echo "| stage | status | wall s | headline | output |"
        echo "|---|---|---|---|---|"
        for i in "${!NAMES[@]}"; do
            name="${NAMES[$i]}"
            headline=""
            [ -f "$RUN_DIR/$name/headline.txt" ] && headline="$(tr '|\n' '/ ' < "$RUN_DIR/$name/headline.txt" | sed 's/ *$//')"
            if [ -d "$RUN_DIR/$name" ]; then
                echo "| $name | ${STATUS[$i]} | ${WALL[$i]} | $headline | \`$(rel "$RUN_DIR/$name")\` |"
            else
                echo "| $name | ${STATUS[$i]} | ${WALL[$i]} | $headline | |"
            fi
        done
    } > "$RUN_DIR/SUMMARY.md"
}

stop_stage() {
    # a stage cut short by a signal: stop its subshell and whatever it started
    # (the stack is not below it, and goes down with stack_down)
    [ -n "$STAGE_PID" ] && kill -0 "$STAGE_PID" 2> /dev/null || return 0
    local all=() i
    mapfile -t all < <(descendants "$STAGE_PID")
    all+=("$STAGE_PID")
    kill -TERM "${all[@]}" 2> /dev/null
    for ((i = 0; i < 20; i++)); do
        [ -z "$(alive "${all[@]}")" ] && break
        sleep 0.5
    done
    kill -KILL $(alive "${all[@]}") 2> /dev/null
    echo "stopped the $STAGE_NAME stage: ${all[*]}"
}

finish() {
    local code=$? t0 left
    trap - EXIT INT TERM HUP
    stop_stage
    while [ ${#STATUS[@]} -lt ${#NAMES[@]} ]; do
        STATUS+=("interrupted")
        WALL+=("$(seconds_since "$STAGE_T0")")
    done
    NAMES+=("teardown")
    STAGE_DIR="$RUN_DIR/teardown"
    mkdir -p "$STAGE_DIR"
    t0="$EPOCHREALTIME"
    echo
    echo "== teardown"
    if [ "$KEEP_STACK" = 1 ] && [ "$code" = 0 ] && [ -s "$STACK_PIDS" ]; then
        headline "kept up on request: $(awk '{ print $1 "=" $2 }' "$STACK_PIDS" | tr '\n' ' ')- Flask at $PERFECT_URL"
        echo "stop it with: kill \$(awk '{ print \$2 }' $(rel "$STACK_PIDS"))"
        STATUS+=("kept")
    else
        stack_down | tee "$STAGE_DIR/stage.log"
        left=""
        for port in "$REDIS_PORT" "$FLASK_PORT" "$RUNNER_PORT"; do
            port_listening "$port" && left+="$port "
        done
        if [ -z "$left" ] && [ -z "$(alive $(awk '{ print $3 }' "$RUN_DIR/stack-history.txt"))" ]; then
            headline "$(wc -l < "$RUN_DIR/stack-history.txt") stack processes started in the run, none left; nothing listening on $REDIS_PORT, $FLASK_PORT, $RUNNER_PORT"
            STATUS+=("ok")
        else
            headline "still listening: ${left:-none}; still running: $(alive $(awk '{ print $3 }' "$RUN_DIR/stack-history.txt") | tr '\n' ' ')"
            STATUS+=("failed")
            [ "$code" = 0 ] && code=1
        fi
    fi
    WALL+=("$(seconds_since "$t0")")
    write_summary "$code"
    echo
    cat "$RUN_DIR/SUMMARY.md"
    exit "$code"
}
trap finish EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
trap 'exit 129' HUP

echo "run $RUN_ID in $(rel "$RUN_DIR"): ${SELECTED% }"
FAILED=0
for f in "${RUN[@]}"; do
    STAGE_NAME="$(stage_name "$f")"
    NAMES+=("$STAGE_NAME")
    if [ "$FAILED" = 1 ]; then
        STATUS+=("not run")
        WALL+=("")
        continue
    fi
    STAGE_DIR="$RUN_DIR/$STAGE_NAME"
    mkdir -p "$STAGE_DIR"
    echo
    echo "== $STAGE_NAME: $(stage_field "$f" STAGE_TITLE)"
    STAGE_T0="$EPOCHREALTIME"
    # in the background, so that a signal to run.sh is handled at once rather
    # than after the stage ends; the handler stops the stage
    ( source "$f"; stage_run ) &
    STAGE_PID=$!
    wait "$STAGE_PID"
    code=$?
    STAGE_PID=""
    WALL+=("$(seconds_since "$STAGE_T0")")
    if [ "$code" != 0 ]; then
        echo "stage $STAGE_NAME failed (exit $code); see $(rel "$STAGE_DIR")"
        STATUS+=("failed")
        FAILED=1
    elif [ -f "$STAGE_DIR/skipped" ]; then
        STATUS+=("skipped")
    else
        STATUS+=("ok")
    fi
done

exit "$FAILED"
