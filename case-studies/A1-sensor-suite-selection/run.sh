#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT/trades-x"
exec env -u PYTHONPATH uv run python case-studies/sensor-suite/run_case_study.py "$@"
