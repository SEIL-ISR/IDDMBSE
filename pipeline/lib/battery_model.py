# Write the UPPAAL model of the SysML battery state machine to the path given.
#
# The same translation veritas/formal/sysml2uppaal/demo_battery.py makes -- the
# mk6 model's state machine and the Demo AD activity, scale 100, the same two
# requirement bindings -- written where the pipeline wants it instead of next
# to the demo. Runs in VERITAS's environment:
#
#   uv run --project veritas python pipeline/lib/battery_model.py <out.xml>

import pathlib
import sys

repo = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(repo / "veritas" / "formal" / "sysml2uppaal"))
from sysml2uppaal import translate  # noqa: E402

model = repo / "sysml" / "models" / "AGR_stack-MB-SensorTrade-mk6.mdzip"
out = sys.argv[1]
aliases = {
    "current_soc": ["state of charge"],
    "gt": ["complete the entire path"],
}
templates, queries, warnings = translate(
    str(model), out, scale=100, aliases=aliases,
    state_machines=["ee_hv_battery_charge_discharge"], activities=["Demo AD"])
print("wrote", out, "from", model.name + ":", len(templates), "templates,",
      len(queries), "queries,", len(warnings), "warnings")
