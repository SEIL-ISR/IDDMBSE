#!/usr/bin/env bash
# Start Nav2 (warehouse_nav2.launch.py) in the tmux session iddmbse-nav2 on the
# host's ROS 2 Jazzy, on the same domain and middleware as launch_stream.sh:
# IDDMBSE_ROS_DOMAIN_ID (default 87) and rmw_fastrtps_cpp. Extra arguments go
# to ros2 launch (for example map:=...). The log is /tmp/iddmbse-nav2.log and
# the launch PID goes to /tmp/iddmbse-nav2.pid; ../stop.sh nav2 stops it.
set -euo pipefail

here=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
domain=${IDDMBSE_ROS_DOMAIN_ID:-87}
session=iddmbse-nav2
log=/tmp/iddmbse-nav2.log
pidfile=/tmp/iddmbse-nav2.pid

if tmux has-session -t "$session" 2>/dev/null; then
  echo "tmux session $session already exists"; exit 1
fi
rm -f "$pidfile"
# a clean environment: the tmux server may carry another project's ROS and Python settings
tmux new-session -d -s "$session" env -i HOME="$HOME" USER="$USER" LANG=C.UTF-8 TERM=xterm-256color \
  PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin bash -c "
  source /opt/ros/jazzy/setup.bash
  export ROS_DOMAIN_ID=$domain RMW_IMPLEMENTATION=rmw_fastrtps_cpp ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST
  echo \$\$ > $pidfile
  exec ros2 launch '$here/warehouse_nav2.launch.py' $* > $log 2>&1
"
echo "started tmux session $session, log $log"
