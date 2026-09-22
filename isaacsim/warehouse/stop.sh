#!/usr/bin/env bash
# Stop what launch_stream.sh and nav2/start_nav2.sh started, by the PIDs they
# recorded, and nothing else: Nav2 first (SIGINT to its process group, then
# SIGKILL after 30 s), then the Kit (SIGTERM, then SIGKILL after 90 s) and the
# helper processes it started, then the two tmux sessions.
#
#   ./stop.sh          both
#   ./stop.sh nav2     Nav2 only
#   ./stop.sh kit      the Kit only
set -uo pipefail

stop_group() {  # name pidfile first-signal grace-seconds
  local name=$1 pidfile=$2 sig=$3 grace=$4 pid children
  if [ ! -f "$pidfile" ]; then echo "$name: no $pidfile"; return; fi
  pid=$(cat "$pidfile")
  if ! kill -0 "$pid" 2>/dev/null; then echo "$name: $pid not running"; rm -f "$pidfile"; return; fi
  children=$(pgrep -P "$pid" | tr '\n' ' ')
  echo "$name: $sig to process group $pid (children $children)"
  kill "-$sig" -- "-$pid" 2>/dev/null || kill "-$sig" "$pid"
  timeout "$grace" tail --pid="$pid" -f /dev/null
  if kill -0 "$pid" 2>/dev/null; then
    echo "$name: still alive after $grace s, SIGKILL"
    kill -KILL -- "-$pid" 2>/dev/null || kill -KILL "$pid"
  fi
  for child in $children; do
    kill -0 "$child" 2>/dev/null && { echo "$name: child $child still alive, SIGKILL"; kill -KILL "$child"; }
  done
  rm -f "$pidfile"
  echo "$name: stopped"
}

what=${1:-all}
if [ "$what" = all ] || [ "$what" = nav2 ]; then
  stop_group nav2 /tmp/iddmbse-nav2.pid INT 30
  tmux has-session -t iddmbse-nav2 2>/dev/null && tmux kill-session -t iddmbse-nav2
fi
if [ "$what" = all ] || [ "$what" = kit ]; then
  stop_group kit /tmp/iddmbse-kit.pid TERM 90
  tmux has-session -t iddmbse-kit 2>/dev/null && tmux kill-session -t iddmbse-kit
fi
exit 0
