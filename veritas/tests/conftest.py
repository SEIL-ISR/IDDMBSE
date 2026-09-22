import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]

# the vendored trees keep their upstream flat-import layout, so each one goes on the path;
# the modules written for this release sit beside them the same way
for d in ["formal/bt2automata", "runtime/tbt-monitor", "synthesis/ltbt",
          "formal", "formal/sysml2uppaal", "datadriven", "runtime/stl-observer"]:
    sys.path.insert(0, str(root / d))
