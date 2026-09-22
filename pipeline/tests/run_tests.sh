#!/usr/bin/env bash
# Tests for pipeline/run.sh that need no campaign: the scripts parse, --list and
# --dry-run name the right stages and start nothing, a port in use is refused,
# and a stage that fails with a PERFECT stack up and a trial running leaves no
# process behind.
#
#   bash pipeline/tests/run_tests.sh
#
# Every port it uses is one the kernel hands out as free at the time, and every
# process it starts is stopped before it exits.

set -u

TESTS="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PIPELINE="$(dirname "$TESTS")"
REPO="$(dirname "$PIPELINE")"
RUN="$PIPELINE/run.sh"
TMP="$(mktemp -d /tmp/pipeline-tests-XXXXXX)"
SERVER_PID=""
PASSED=0
FAILED=0

cleanup() {
    [ -n "$SERVER_PID" ] && kill "$SERVER_PID" 2> /dev/null
    rm -rf "$TMP"
}
trap cleanup EXIT

ok() { echo "ok $1"; PASSED=$((PASSED + 1)); }
fail() { echo "FAIL $1: $2"; FAILED=$((FAILED + 1)); }

free_port() {
    python3 -c "import socket; s = socket.socket(); s.bind(('127.0.0.1', 0)); print(s.getsockname()[1]); s.close()"
}

listening() { ss -ltn "sport = :$1" | grep -q LISTEN; }

redis_pids() { pgrep -x redis-server | sort | tr '\n' ' '; }

# ------------------------------------------------------------------
# the scripts parse

bad=""
for f in "$RUN" "$PIPELINE"/lib/*.sh "$PIPELINE"/stages/*.sh "$TESTS"/*.sh; do
    bash -n "$f" || bad+="$(basename "$f") "
done
[ -z "$bad" ] && ok "bash -n over every script" || fail "bash -n" "$bad"

# ------------------------------------------------------------------
# --list and --dry-run

expected="00-preflight 10-sensor-suite 20-rarrt-planning 30-conformal-calibration 40-isaacsim-range 50-veritas-report 60-uppaal 70-stl-replay summary teardown"
got="$(bash "$RUN" --list | awk '{ print $1 }' | tr '\n' ' ')"
[ "$got" = "$expected " ] && ok "--list names every stage in order" || fail "--list" "got: $got"

dry_stages() {
    # the stage headers a dry run prints, in order
    bash "$RUN" --dry-run --out "$TMP/dry" "$@" | sed -n 's/^== \([^:]*\).*/\1/p' | tr '\n' ' '
}

before="$(redis_pids)"
got="$(dry_stages)"
[ "$got" = "preflight sensor-suite veritas-report uppaal stl-replay summary teardown " ] \
    && ok "--dry-run runs the default stages" || fail "--dry-run" "got: $got"
got="$(dry_stages --all)"
[ "$got" = "preflight sensor-suite rarrt-planning conformal-calibration veritas-report uppaal stl-replay summary teardown " ] \
    && ok "--dry-run --all adds the two campaigns" || fail "--dry-run --all" "got: $got"
got="$(dry_stages --range)"
[ "$got" = "preflight sensor-suite isaacsim-range veritas-report uppaal stl-replay summary teardown " ] \
    && ok "--dry-run --range adds the range campaign" || fail "--dry-run --range" "got: $got"

commands="$(bash "$RUN" --dry-run --out "$TMP/dry")"
if echo "$commands" | grep -q "run_ddo_campaign.py --submit" \
    && echo "$commands" | grep -q "report.py --db project.db" \
    && echo "$commands" | grep -q "replay_observer.py"; then
    ok "--dry-run prints the campaign, report and replay commands"
else
    fail "--dry-run commands" "a campaign, report or replay command is missing"
fi
if [ ! -e "$TMP/dry" ] && [ "$(redis_pids)" = "$before" ]; then
    ok "--dry-run writes no run directory and starts no Redis"
else
    fail "--dry-run side effects" "run directory $( [ -e "$TMP/dry" ] && echo written || echo absent ), redis-server $before -> $(redis_pids)"
fi

# ------------------------------------------------------------------
# a port in use is refused before anything starts

busy="$(free_port)"
python3 -m http.server "$busy" --bind 127.0.0.1 > /dev/null 2>&1 &
SERVER_PID=$!
for _ in $(seq 20); do
    listening "$busy" && break
    sleep 0.25
done
if listening "$busy"; then
    out="$(PIPELINE_REDIS_PORT="$(free_port)" PIPELINE_FLASK_PORT="$busy" PIPELINE_RUNNER_PORT="$(free_port)" \
        timeout 60 bash "$RUN" --out "$TMP/refused" 2>&1)"
    code=$?
    if [ "$code" = 1 ] && echo "$out" | grep -q "port $busy is already in use" && [ ! -e "$TMP/refused" ] \
        && [ "$(redis_pids)" = "$before" ]; then
        ok "a port already listening is refused and nothing starts"
    else
        fail "port refusal" "exit $code, output: $(echo "$out" | head -3 | tr '\n' ' ')"
    fi
else
    fail "port refusal" "the throwaway http.server did not listen on $busy"
fi
kill "$SERVER_PID" 2> /dev/null
wait "$SERVER_PID" 2> /dev/null
if kill -0 "$SERVER_PID" 2> /dev/null || listening "$busy"; then
    fail "port refusal cleanup" "http.server $SERVER_PID still up"
fi
SERVER_PID=""

# ------------------------------------------------------------------
# a stage that fails with a stack up and a trial running leaves nothing behind

mkdir -p "$TMP/stages"
cat > "$TMP/stages/00-fails.sh" <<'STAGE'
STAGE_WHEN=default
STAGE_TITLE="bring a PERFECT stack up on the dummy example, start a trial, then fail"

stage_run() {
    stack_up "$REPO/perfect/examples/dummy" || return 1
    perfect_run python -m flask --app perfect.app components load_component_implementations components.json
    perfect_run python -m flask --app perfect.app designs create "Widget A" "Dijkstra" -i --name "Widget A + Dijkstra" --tag demo
    perfect_run python -m flask --app perfect.app environments create_explicit "Nothing" '{}' -t demo
    perfect_run python -m flask --app perfect.app experiments create demo demo -t demo
    perfect_run python -m flask --app perfect.app experiments run demo
    # the trial's countdown runs as a child of the runner; wait for it, then fail
    local runner i below=""
    runner="$(awk '$1 == "runner" { print $2 }' "$STACK_PIDS")"
    for ((i = 0; i < 30; i++)); do
        below="$(descendants "$runner" | tr '\n' ' ')"
        [ -n "$below" ] && break
        sleep 1
    done
    echo "$below" > "$STAGE_DIR/below-runner.txt"
    echo "failing on purpose, with $below running below the runner"
    return 1
}
STAGE
cat > "$TMP/stages/10-after.sh" <<'STAGE'
STAGE_WHEN=default
STAGE_TITLE="must not run after a failed stage"
stage_run() { echo "ran"; }
STAGE

ports=("$(free_port)" "$(free_port)" "$(free_port)")
out="$(PIPELINE_STAGES="$TMP/stages" PIPELINE_REDIS_PORT="${ports[0]}" PIPELINE_FLASK_PORT="${ports[1]}" \
    PIPELINE_RUNNER_PORT="${ports[2]}" timeout 180 bash "$RUN" --out "$TMP/failing" 2>&1)"
code=$?
run_dir="$TMP/failing"
started="$(awk '{ print $3 }' "$run_dir/stack-history.txt" 2> /dev/null | tr '\n' ' ')"
below="$(cat "$run_dir/fails/below-runner.txt" 2> /dev/null)"
alive=""
for p in $started $below; do
    kill -0 "$p" 2> /dev/null && alive+="$p "
done
open=""
for p in "${ports[@]}"; do
    listening "$p" && open+="$p "
done

[ "$code" = 1 ] && ok "a failing stage makes the run exit 1" || fail "failing stage exit" "exit $code"
[ "$(echo "$started" | wc -w)" = 4 ] && [ -n "$below" ] \
    && ok "the failing stage had a stack of 4 processes and a trial below the runner ($below)" \
    || fail "failing stage setup" "started: $started; below the runner: $below"
[ -z "$alive" ] && [ -z "$open" ] \
    && ok "after the failure every process is gone and no port is listening" \
    || fail "teardown after failure" "alive: $alive; listening: $open"
grep -q "^| fails | failed |" "$run_dir/SUMMARY.md" 2> /dev/null && grep -q "^| after | not run |" "$run_dir/SUMMARY.md" \
    && grep -q "^| teardown | ok |" "$run_dir/SUMMARY.md" \
    && ok "SUMMARY.md marks the stage failed, the next not run and the teardown ok" \
    || fail "SUMMARY.md after failure" "$(grep '^|' "$run_dir/SUMMARY.md" 2> /dev/null | tr '\n' ' ')"
echo "$out" | grep -q "^ran$" && fail "stage order" "the stage after the failure ran" || true

# ------------------------------------------------------------------
# --keep-stack leaves the last stack up after a run that succeeds, and the
# command the summary prints stops it

mkdir -p "$TMP/kept-stages"
cat > "$TMP/kept-stages/00-up.sh" <<'STAGE'
STAGE_WHEN=default
STAGE_TITLE="bring a PERFECT stack up on the dummy example and release it"
stage_run() {
    stack_up "$REPO/perfect/examples/dummy" || return 1
    stack_release
}
STAGE
ports=("$(free_port)" "$(free_port)" "$(free_port)")
out="$(PIPELINE_STAGES="$TMP/kept-stages" PIPELINE_REDIS_PORT="${ports[0]}" PIPELINE_FLASK_PORT="${ports[1]}" \
    PIPELINE_RUNNER_PORT="${ports[2]}" timeout 120 bash "$RUN" --keep-stack --out "$TMP/kept" 2>&1)"
code=$?
kept="$(awk '{ print $2 }' "$TMP/kept/stack.pids" 2> /dev/null | tr '\n' ' ')"
http="$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:${ports[1]}/")"
[ "$code" = 0 ] && [ "$(echo "$kept" | wc -w)" = 4 ] && [ "$http" = 200 ] \
    && grep -q "^| teardown | kept |" "$TMP/kept/SUMMARY.md" \
    && ok "--keep-stack leaves the stack up and answering on its Flask port" \
    || fail "--keep-stack" "exit $code, kept: $kept, http $http"
stop="$(echo "$out" | sed -n 's/^stop it with: //p')"
# the path in it is relative to the repository when the run directory is inside it
(cd "$REPO" && eval "$stop")
for _ in $(seq 20); do
    [ -z "$(for p in $kept; do kill -0 "$p" 2> /dev/null && echo "$p"; done)" ] && break
    sleep 0.5
done
alive=""
for p in $kept; do
    kill -0 "$p" 2> /dev/null && alive+="$p "
done
if [ -n "$stop" ] && [ -z "$alive" ]; then
    ok "the printed stop command stops the kept stack"
else
    fail "stopping the kept stack" "command: $stop; still alive: $alive"
    [ -n "$alive" ] && kill $alive 2> /dev/null
fi

# ------------------------------------------------------------------
# Ctrl-C (SIGINT) or a kill (SIGTERM) in the middle of a stage stops the
# stage and the stack at once

mkdir -p "$TMP/slow-stages"
cat > "$TMP/slow-stages/00-slow.sh" <<'STAGE'
STAGE_WHEN=default
STAGE_TITLE="bring a PERFECT stack up on the dummy example, then wait two minutes"
stage_run() {
    stack_up "$REPO/perfect/examples/dummy" || return 1
    sleep 120 &
    echo "$!" > "$STAGE_DIR/sleep.pid"
    wait
}
STAGE

interrupt() {
    # interrupt <signal>: start a run in its own process group, send the signal
    # once its stack is up, and print its exit code and how many seconds it
    # took to stop. SIGINT goes to the whole group, as Ctrl-C in a terminal
    # sends it; SIGTERM to run.sh alone, as `kill` does. SIGINT is reset to its
    # default first, because a shell started in the background ignores it.
    python3 - "$1" "$RUN" "$TMP/interrupted-$1" "$TMP/slow-stages" "$(free_port)" "$(free_port)" "$(free_port)" <<'PY'
import os, signal, subprocess, sys, time
sig, run, out, stages, redis, flask, runner = sys.argv[1:]
env = dict(os.environ, PIPELINE_STAGES=stages, PIPELINE_REDIS_PORT=redis,
           PIPELINE_FLASK_PORT=flask, PIPELINE_RUNNER_PORT=runner)
p = subprocess.Popen(["bash", run, "--out", out], env=env, stdout=subprocess.DEVNULL,
                     stderr=subprocess.STDOUT, start_new_session=True,
                     preexec_fn=lambda: signal.signal(signal.SIGINT, signal.SIG_DFL))
pids = os.path.join(out, "stack.pids")
for _ in range(120):
    if os.path.exists(os.path.join(out, "slow", "sleep.pid")):
        break
    time.sleep(0.5)
sent = time.monotonic()
if sig == "SIGINT":
    os.killpg(p.pid, signal.SIGINT)
else:
    p.send_signal(signal.SIGTERM)
code = p.wait(timeout=120)
print(code, round(time.monotonic() - sent, 1))
PY
}

for sig in SIGINT SIGTERM; do
    read -r code seconds <<< "$(interrupt "$sig")"
    run_dir="$TMP/interrupted-$sig"
    started="$(awk '{ print $3 }' "$run_dir/stack-history.txt" 2> /dev/null | tr '\n' ' ')"
    alive=""
    for p in $started $(cat "$run_dir/slow/sleep.pid" 2> /dev/null); do
        kill -0 "$p" 2> /dev/null && alive+="$p "
    done
    if [ "$(echo "$started" | wc -w)" = 4 ] && [ -z "$alive" ] && [ "${code:-}" != 0 ] \
        && grep -q "^| slow | interrupted |" "$run_dir/SUMMARY.md" 2> /dev/null \
        && grep -q "^| teardown | ok |" "$run_dir/SUMMARY.md"; then
        ok "$sig to $( [ "$sig" = SIGINT ] && echo "the process group, as Ctrl-C" || echo "run.sh alone") in the middle of a stage: exit $code after $seconds s, stage and stack stopped, SUMMARY.md written"
    else
        fail "$sig" "exit ${code:-none} after ${seconds:-?} s; started: $started; alive: $alive"
    fi
done

echo "$PASSED passed, $FAILED failed"
[ "$FAILED" = 0 ]
