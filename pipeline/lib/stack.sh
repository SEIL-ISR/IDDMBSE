# The private PERFECT stack a campaign stage runs against: Redis, an RQ worker,
# the experiment runner and the Flask server, brought up the way
# perfect/devtools/smoke_dummy.sh brings them up, on a copy of one example under
# the stage's directory, so the database is new and the example stays as it is.
#
# Ports come from run.sh (PIPELINE_REDIS_PORT, PIPELINE_FLASK_PORT,
# PIPELINE_RUNNER_PORT; 6390, 5001, 8003). Every process started is written to
# $RUN_DIR/stack.pids ("name pid") while it is up, and to
# $RUN_DIR/stack-history.txt for good. stack_down stops exactly those processes
# and whatever they started, and nothing else.
#
# Sourced, never run; needs lib/log.sh.

PERFECT_VENV="$REPO/perfect/.venv"
PERFECT_URL="http://127.0.0.1:$FLASK_PORT"
STACK_PIDS="$RUN_DIR/stack.pids"

port_listening() {
    ss -ltn "sport = :$1" | grep -q LISTEN
}

ports_free() {
    # a port that is already listening belongs to someone else: say so and refuse
    local port busy=0
    for port in "$REDIS_PORT" "$FLASK_PORT" "$RUNNER_PORT"; do
        if port_listening "$port"; then
            echo "port $port is already in use by another process"
            busy=1
        fi
    done
    return "$busy"
}

wait_for() {
    # wait_for <tries> <command...>: once a second until it succeeds, at most <tries> times
    local tries="$1" i
    shift
    for ((i = 0; i < tries; i++)); do
        "$@" > /dev/null 2>&1 && return 0
        sleep 1
    done
    return 1
}

redis_up() { redis-cli -p "$REDIS_PORT" ping 2>/dev/null | grep -q PONG; }
flask_up() { [ "$(curl -s -o /dev/null -w '%{http_code}' "$PERFECT_URL/")" = 200 ]; }
runner_up() { port_listening "$RUNNER_PORT"; }

copy_example() {
    # everything the example runs from, but not its tests, database or README
    find "$1" -mindepth 1 -maxdepth 1 ! -name tests ! -name migrations ! -name __pycache__ \
        ! -name '*.db*' ! -name README.md -exec cp -rp {} "$2"/ \;
}

stack_up() {
    # stack_up <example directory>: copy the example to $STAGE_DIR/project and
    # bring the four processes up on it
    local example="$1" logs="$STAGE_DIR/stack-logs"
    STACK_PROJECT="$STAGE_DIR/project"
    if [ "$DRY_RUN" = 1 ]; then
        echo "+ copy $(rel "$example") to $(rel "$STACK_PROJECT")"
        show redis-server --port "$REDIS_PORT" --save '' --appendonly no --dir "$STAGE_DIR/redis"
        show python -m flask --app perfect.app db init
        show python -m flask --app perfect.app db migrate -m "Initial migration."
        show python -m flask --app perfect.app db upgrade
        show rq worker perfect-tasks --url "redis://127.0.0.1:$REDIS_PORT"
        show python -m perfect.experiment.runner
        show python -m flask --app perfect.app run --port "$FLASK_PORT"
        return 0
    fi

    stack_down   # a stack an earlier stage kept up goes first
    ports_free || return 1
    mkdir -p "$STACK_PROJECT" "$STAGE_DIR/redis" "$logs"
    copy_example "$example" "$STACK_PROJECT"
    (
        started() {
            echo "$1 $2" >> "$STACK_PIDS"
            echo "$STAGE_NAME $1 $2" >> "$RUN_DIR/stack-history.txt"
        }
        flask_cli() {
            python -m flask --app perfect.app "$@" >> "$logs/cli.log" 2>&1 \
                || { echo "flask $* failed; see $(rel "$logs")/cli.log"; exit 1; }
        }
        # shellcheck disable=SC1091
        source "$PERFECT_VENV/bin/activate"
        export PERFECT_PROJECT_ROOT="$STACK_PROJECT" REDIS_URL="redis://127.0.0.1:$REDIS_PORT" RUNNER_PORT
        cd "$STACK_PROJECT" || exit 1

        redis-server --port "$REDIS_PORT" --save '' --appendonly no --dir "$STAGE_DIR/redis" \
            > "$logs/redis.log" 2>&1 &
        started redis $!
        wait_for 10 redis_up || { echo "Redis did not come up on $REDIS_PORT"; exit 1; }

        flask_cli db init
        flask_cli db migrate -m "Initial migration."
        flask_cli db upgrade

        rq worker perfect-tasks --url "$REDIS_URL" > "$logs/worker.log" 2>&1 &
        started worker $!
        python -m perfect.experiment.runner > "$logs/runner.log" 2>&1 &
        started runner $!
        python -m flask --app perfect.app run --port "$FLASK_PORT" > "$logs/flask.log" 2>&1 &
        started flask $!

        wait_for 15 flask_up || { echo "the Flask server did not answer on $FLASK_PORT"; exit 1; }
        wait_for 15 runner_up || { echo "the runner did not listen on $RUNNER_PORT"; exit 1; }
    ) || { stack_down; return 1; }
    echo "PERFECT stack up on $(rel "$STACK_PROJECT"): Redis $REDIS_PORT, Flask $FLASK_PORT, runner $RUNNER_PORT;" \
        "pids $(awk '{ print $1 "=" $2 }' "$STACK_PIDS" | tr '\n' ' ')"
}

perfect_run() {
    # a command in the PERFECT environment, in the stack's project directory
    if [ "$DRY_RUN" = 1 ]; then
        show "$@"
        return 0
    fi
    (
        # shellcheck disable=SC1091
        source "$PERFECT_VENV/bin/activate"
        export PERFECT_PROJECT_ROOT="$STACK_PROJECT" REDIS_URL="redis://127.0.0.1:$REDIS_PORT" RUNNER_PORT
        cd "$STACK_PROJECT" && step "$@"
    )
}

descendants() {
    # every process below the given ones, children first found first
    local frontier=("$@") next p child
    while [ ${#frontier[@]} -gt 0 ]; do
        next=()
        for p in "${frontier[@]}"; do
            for child in $(pgrep -P "$p"); do
                next+=("$child")
                echo "$child"
            done
        done
        frontier=("${next[@]}")
    done
}

alive() {
    local p
    for p in "$@"; do
        kill -0 "$p" 2> /dev/null && echo "$p"
    done
}

stack_down() {
    # stop what stack_up started, and whatever those processes started (a
    # trial's simulator runs in its own session but is still their child):
    # TERM, up to 15 s to go, then KILL
    [ -s "$STACK_PIDS" ] || return 0
    local names=() pids=() all=() left=() name pid i
    while read -r name pid; do
        names+=("$name")
        pids+=("$pid")
    done < "$STACK_PIDS"
    mapfile -t all < <(descendants "${pids[@]}")
    all+=("${pids[@]}")
    kill -TERM "${all[@]}" 2> /dev/null
    for ((i = 0; i < 30; i++)); do
        mapfile -t left < <(alive "${all[@]}")
        [ ${#left[@]} -eq 0 ] && break
        sleep 0.5
    done
    if [ ${#left[@]} -gt 0 ]; then
        echo "still running after 15 s, sent KILL: ${left[*]}"
        kill -KILL "${left[@]}" 2> /dev/null
        sleep 1
    fi
    mapfile -t left < <(alive "${all[@]}")
    : > "$STACK_PIDS"
    local stopped=""
    for i in "${!pids[@]}"; do
        stopped+="${names[$i]}=${pids[$i]} "
    done
    echo "PERFECT stack down: stopped ${stopped}and $((${#all[@]} - ${#pids[@]})) processes they started"
    if [ ${#left[@]} -gt 0 ]; then
        echo "not stopped: ${left[*]}"
        return 1
    fi
}

stack_release() {
    # end of a campaign stage: the stack goes down unless --keep-stack asked
    # for the last one to stay up
    [ "$DRY_RUN" = 1 ] && return 0
    [ "${KEEP_STACK:-0}" = 1 ] || stack_down
}
