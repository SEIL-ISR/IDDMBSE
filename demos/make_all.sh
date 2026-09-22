#!/usr/bin/env bash
# Render the five animations into animations/<name>/.
# A sourced ROS 2 environment puts its site-packages on PYTHONPATH; the demos do not need it.
set -euo pipefail
cd "$(dirname "$0")"
for name in mavf_ranking_flip range_replay multirobot_room rarrt_noise_sweep calibration_curve; do
    echo "== $name"
    env -u PYTHONPATH uv run python "animations/$name/make.py" "$@"
done
