#!/usr/bin/env bash
# Sources ROS 2 and, once the workspace has been built, its install space.
set -e
source "/opt/ros/${ROS2_DISTRO}/setup.bash"
if [ -f "${WORKSPACE_PATH}/install/local_setup.bash" ]; then
    source "${WORKSPACE_PATH}/install/local_setup.bash"
fi
exec "$@"
