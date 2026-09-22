#!/usr/bin/env bash
# Compose the example behavior tree into an UPPAAL model. With --verify, check the model's
# queries with verifyta as well, when an UPPAAL install is on the machine.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT/veritas"

VERIFY=0
ARGS=()
for a in "$@"; do
  if [ "$a" = "--verify" ]; then VERIFY=1; else ARGS+=("$a"); fi
done

OUT="${ARGS[0]:-$ROOT/veritas/formal/bt2automata/BT_converted.xml}"
env -u PYTHONPATH uv run python formal/bt2automata/demo.py "$OUT"

if [ "$VERIFY" = "1" ]; then
  if env -u PYTHONPATH uv run python formal/verify.py "$OUT" --out "$(dirname "$OUT")"; then
    :
  else
    status=$?
    # 2 is "no verifyta on this machine", which leaves the written model as the result
    if [ "$status" != "2" ]; then exit "$status"; fi
  fi
fi
