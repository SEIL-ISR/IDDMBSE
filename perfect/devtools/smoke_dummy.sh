#!/usr/bin/env bash
# Unattended end-to-end check of the PERFECT stack on the dummy example.
#
# It runs the bring-up recorded in README.md ("Bring-up, as measured") against a
# throwaway copy of examples/dummy in a temporary directory, on its own Redis,
# Flask and runner ports, then reads the result back through the JSON API and
# tears everything down. Exit 0 means the trial reached SHUT_DOWN and the API
# reported it; exit 1 means it did not.
#
#   perfect/devtools/smoke_dummy.sh [--redis-port N] [--flask-port N]
#                                   [--runner-port N] [--no-api-run] [--keep]
#
# Nothing it starts outlives the script: every process it launches is killed on
# exit, including on failure.

set -u

REDIS_PORT=6390
FLASK_PORT=5001
RUNNER_PORT=8003
API_RUN=1
KEEP=0

while [ $# -gt 0 ]; do
    case "$1" in
        --redis-port) REDIS_PORT="$2"; shift 2 ;;
        --flask-port) FLASK_PORT="$2"; shift 2 ;;
        --runner-port) RUNNER_PORT="$2"; shift 2 ;;
        --no-api-run) API_RUN=0; shift ;;
        --keep) KEEP=1; shift ;;
        *) echo "unknown argument $1"; exit 2 ;;
    esac
done

PERFECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="$PERFECT_ROOT/.venv"
PROJECT_ROOT="$(mktemp -d /tmp/perfect-smoke-XXXXXX)"
REDIS_DIR="$PROJECT_ROOT/redis"
LOG_DIR="$PROJECT_ROOT/logs"
mkdir -p "$REDIS_DIR" "$LOG_DIR"

REDIS_PID=""
WORKER_PID=""
RUNNER_PID=""
FLASK_PID=""

cleanup() {
    for pid in "$FLASK_PID" "$RUNNER_PID" "$WORKER_PID" "$REDIS_PID"; do
        [ -n "$pid" ] && kill "$pid" 2>/dev/null
    done
    for pid in "$FLASK_PID" "$RUNNER_PID" "$WORKER_PID" "$REDIS_PID"; do
        [ -n "$pid" ] && wait "$pid" 2>/dev/null
    done
    if [ "$KEEP" = "1" ]; then
        echo "kept $PROJECT_ROOT"
    else
        rm -rf "$PROJECT_ROOT"
    fi
}
trap cleanup EXIT

fail() {
    echo "FAIL: $*"
    [ -n "$WORKER_PID" ] && tail -20 "$LOG_DIR/worker.log"
    [ -n "$RUNNER_PID" ] && tail -20 "$LOG_DIR/runner.log"
    exit 1
}

# A port already in use belongs to someone else. Do not touch it.
for port in "$REDIS_PORT" "$FLASK_PORT" "$RUNNER_PORT"; do
    if ss -ltn "sport = :$port" | grep -q LISTEN; then
        echo "FAIL: port $port is already in use by another process"
        exit 1
    fi
done

[ -d "$VENV" ] || fail "no virtual environment at $VENV (see README.md)"
cp -p "$PERFECT_ROOT"/examples/dummy/experiment.py \
      "$PERFECT_ROOT"/examples/dummy/components.json \
      "$PERFECT_ROOT"/examples/dummy/countdown.bash "$PROJECT_ROOT"/

# shellcheck disable=SC1091
source "$VENV/bin/activate"
export PERFECT_PROJECT_ROOT="$PROJECT_ROOT"
export REDIS_URL="redis://127.0.0.1:$REDIS_PORT"
export RUNNER_PORT
cd "$PROJECT_ROOT" || exit 1

API="http://127.0.0.1:$FLASK_PORT/api/v1"

echo "project root $PROJECT_ROOT, redis $REDIS_PORT, flask $FLASK_PORT, runner $RUNNER_PORT"

redis-server --port "$REDIS_PORT" --save '' --appendonly no --dir "$REDIS_DIR" \
    >"$LOG_DIR/redis.log" 2>&1 &
REDIS_PID=$!

# Bounded wait for Redis: 10 checks, 1 s apart.
for _ in $(seq 10); do
    redis-cli -p "$REDIS_PORT" ping 2>/dev/null | grep -q PONG && break
    sleep 1
done
redis-cli -p "$REDIS_PORT" ping 2>/dev/null | grep -q PONG || fail "Redis did not come up on $REDIS_PORT"

flask_cli() { python -m flask --app perfect.app "$@" >>"$LOG_DIR/cli.log" 2>&1; }

flask_cli db init || fail "db init"
flask_cli db migrate -m "Initial migration." || fail "db migrate"
flask_cli db upgrade || fail "db upgrade"
flask_cli components load_component_implementations components.json || fail "components load"
flask_cli designs create "Widget A" "Dijkstra" -i --name "Widget A + Dijkstra" --tag demo || fail "designs create"
flask_cli environments create_explicit "Nothing" '{}' -t demo || fail "environments create_explicit"
flask_cli experiments create demo demo -t demo || fail "experiments create"

rq worker perfect-tasks --url "$REDIS_URL" >"$LOG_DIR/worker.log" 2>&1 &
WORKER_PID=$!
python -m perfect.experiment.runner >"$LOG_DIR/runner.log" 2>&1 &
RUNNER_PID=$!
python -m flask --app perfect.app run --port "$FLASK_PORT" >"$LOG_DIR/flask.log" 2>&1 &
FLASK_PID=$!

# Bounded wait for the server: 10 checks, 1 s apart.
for _ in $(seq 10); do
    [ "$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:$FLASK_PORT/")" = "200" ] && break
    sleep 1
done
[ "$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:$FLASK_PORT/")" = "200" ] \
    || fail "Flask server did not answer on $FLASK_PORT"

# The runner takes a moment to bind its websocket port.
for _ in $(seq 10); do
    ss -ltn "sport = :$RUNNER_PORT" | grep -q LISTEN && break
    sleep 1
done
ss -ltn "sport = :$RUNNER_PORT" | grep -q LISTEN || fail "runner did not listen on $RUNNER_PORT"

state_of() {
    curl -s "$API/experiments/$1" \
        | python -c "import json,sys; print(json.load(sys.stdin)['last_trial_state'])"
}

# Bounded wait for a trial to finish: 10 checks, 5 s apart. The dummy trial is
# 4 s of _init plus a 15 s countdown, so ~20 s.
wait_for_shut_down() {
    for _ in $(seq 10); do
        sleep 5
        case "$(state_of "$1")" in *SHUT_DOWN*) return 0 ;; esac
    done
    return 1
}

echo "--- experiments run demo"
flask_cli experiments run demo || fail "experiments run"
wait_for_shut_down 1 || fail "experiment 1 did not reach SHUT_DOWN (state $(state_of 1))"
echo "experiment 1 state: $(state_of 1)"
curl -s "$API/experiments/1" | python -m json.tool

if [ "$API_RUN" = "1" ]; then
    echo "--- POST /api/v1/run (the payload MatSensorTrade.m sends)"
    RESPONSE=$(curl -s -X POST "$API/run" -H "Content-Type: application/json" -d '{
        "launch_file": "~/auto_stack_ws/src/hardware_launch/launch/navigation_rosbridge.launch",
        "sensor_update": {
            "laser_3d": {"model": "vlp16", "update_rate": 15},
            "camera": {"width": 720, "height": 540, "update_rate": 30, "h_fov": 1.047, "max_range": 50.0},
            "laser_2d": {"update_rate": 25, "max_range": 20.0},
            "depth_camera": {"model": "d435", "width": 1280, "height": 720, "update_rate": 30, "h_fov": 1.5184, "v_fov": 1.0122}
        }
    }')
    echo "$RESPONSE" | python -m json.tool || fail "POST /api/v1/run returned no JSON: $RESPONSE"
    API_ID=$(echo "$RESPONSE" | python -c "import json,sys; print(json.load(sys.stdin)['experiment_id'])")
    wait_for_shut_down "$API_ID" || fail "experiment $API_ID did not reach SHUT_DOWN (state $(state_of "$API_ID"))"
    echo "experiment $API_ID state: $(state_of "$API_ID")"
    curl -s "$API/experiments/$API_ID" | python -m json.tool
fi

echo "PASS"
exit 0
