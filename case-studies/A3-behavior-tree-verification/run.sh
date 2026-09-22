#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT/veritas"
exec env -u PYTHONPATH uv run python formal/bt2automata/demo.py "$@"
