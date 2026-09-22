import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]

# the vendored trees keep their upstream flat-import layout, so each one goes on the path
for d in ["formal/bt2automata", "runtime/tbt-monitor", "synthesis/ltbt"]:
    sys.path.insert(0, str(root / d))
