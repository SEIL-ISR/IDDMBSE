#!/usr/bin/env bash
# Start a headless Isaac Sim 6.0 on GPU 0 with WebRTC streaming, the ROS 2 bridge
# and the python server, in the tmux session iddmbse-kit. It refuses to start when
# a Kit process is running or port 49100 or 8236 is taken.
#
#   ISAACSIM_PATH      the Isaac Sim directory that holds isaac-sim.streaming.sh
#                      (default: a source build under ~/isaacsim)
#   IDDMBSE_STREAM_IP  the address the WebRTC client connects to (default: the
#                      source address of the host's default route, else the first
#                      address hostname -I lists)
#   IDDMBSE_ROS_DOMAIN_ID  the ROS 2 domain (default 87; the shell's own ROS_DOMAIN_ID
#                      is ignored on purpose); the bridge talks rmw_fastrtps_cpp
#
# The log is /tmp/iddmbse-kit.log and the Kit PID goes to /tmp/iddmbse-kit.pid;
# stop.sh stops it. Wait for "app ready" in the log before sending work to the
# python server on 127.0.0.1:8236.
set -euo pipefail

isaacsim=${ISAACSIM_PATH:-$HOME/isaacsim/_build/linux-x86_64/release}
route_dev=$(ip route show default 2>/dev/null | awk '{for (i = 1; i < NF; i++) if ($i == "dev") { print $(i + 1); exit }}')
route_ip=$([ -n "$route_dev" ] && ip -4 -o addr show dev "$route_dev" | awk '{split($4, a, "/"); print a[1]; exit}')
ip=${IDDMBSE_STREAM_IP:-${route_ip:-$(hostname -I | awk '{print $1}')}}
domain=${IDDMBSE_ROS_DOMAIN_ID:-87}
session=iddmbse-kit
log=/tmp/iddmbse-kit.log
pidfile=/tmp/iddmbse-kit.pid
port=8236

if [ ! -x "$isaacsim/isaac-sim.streaming.sh" ]; then
  echo "no isaac-sim.streaming.sh under $isaacsim; set ISAACSIM_PATH"; exit 1
fi
if pgrep -x kit >/dev/null; then
  echo "a Kit process is already running:"; pgrep -ax kit; exit 1
fi
if ss -ltn | grep -qE ":(49100|$port) "; then
  echo "port 49100 or $port is already taken"; exit 1
fi
if tmux has-session -t "$session" 2>/dev/null; then
  echo "tmux session $session already exists"; exit 1
fi

rm -f "$pidfile"
mkdir -p /tmp/iddmbse-kit-run
# a clean environment: the tmux server may carry another project's ROS and Python settings
tmux new-session -d -s "$session" env -i HOME="$HOME" USER="$USER" LANG=C.UTF-8 TERM=xterm-256color \
  PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin bash -c "
  [ -f /opt/ros/jazzy/setup.bash ] && source /opt/ros/jazzy/setup.bash
  export ROS_DOMAIN_ID=$domain RMW_IMPLEMENTATION=rmw_fastrtps_cpp ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST
  export CUDA_VISIBLE_DEVICES=0 OMNI_KIT_ACCEPT_EULA=YES
  cd /tmp/iddmbse-kit-run
  echo \$\$ > $pidfile
  exec '$isaacsim/isaac-sim.streaming.sh' \
    --enable isaacsim.ros2.bridge \
    --enable isaacsim.code_editor.python_server \
    --/exts/isaacsim.code_editor.python_server/port=$port \
    --/app/settings/persistent=0 \
    --/app/file/ignoreUnsavedStage=1 \
    --/renderer/multiGpu/enabled=false \
    --/renderer/activeGpu=0 \
    --/exts/omni.kit.livestream.app/primaryStream/publicIp=$ip \
    --/exts/omni.services.livestream.session/quitOnSessionEnded=false \
    > $log 2>&1
"
echo "started tmux session $session, log $log"
echo "WebRTC client: server $ip (signalling port 49100)"
