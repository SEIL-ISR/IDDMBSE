"""Translate the AGR SysML model's battery state machine into an UPPAAL NTA.

Reads `sysml/models/AGR_stack-MB-SensorTrade-mk6.mdzip` (read-only), translates its one state
machine `ee_hv_battery_charge_discharge` and the small `Demo AD` activity, writes
`battery_sm.xml` next to this script, and prints the templates, locations, edges, queries and
warnings.  The written file is then loaded back with `pyuppaal.UModel` as a check that UPPAAL
will accept it.
"""

import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pyuppaal  # noqa: E402
from sysml2uppaal import translate  # noqa: E402

here = os.path.dirname(os.path.abspath(__file__))
repo = os.path.abspath(os.path.join(here, "..", "..", ".."))
model = os.path.join(repo, "sysml", "models", "AGR_stack-MB-SensorTrade-mk6.mdzip")
out = os.path.join(here, "battery_sm.xml")

# The model has no structured satisfy/verify link between a requirement and a state-machine
# variable -- the guards are free-text OpaqueExpressions -- so the binding is given here, and
# only requirements whose Text matches one of these phrases become proof obligations.
aliases = {
    "current_soc": ["state of charge"],
    "gt": ["complete the entire path"],
}

templates, queries, warnings = translate(
    model, out, scale=100, aliases=aliases,
    state_machines=["ee_hv_battery_charge_discharge"], activities=["Demo AD"])

print("model " + model)
print("wrote " + out)
for t in templates:
    print()
    print("template " + t["name"] + "  (" + t["kind"] + " '" + t["source_name"] + "')")
    print("  locations: " + ", ".join(
        loc["name"] + (" [" + loc["invariant"] + "]" if loc["invariant"] else "")
        for loc in t["locations"]))
    names = {loc["id"]: loc["name"] for loc in t["locations"]}
    for e in t["edges"]:
        print("  edge " + names[e["source"]] + " -> " + names[e["target"]]
              + "  guard: " + str(e["guard"]) + "  assign: " + e["assignment"])

print()
print("queries")
for q in queries:
    print("  " + q["formula"] + "    // " + q["comment"])

print()
print(str(len(warnings)) + " warnings")
for w in warnings:
    print("  " + w)

print()
# pyuppaal 1.2.0 rewrites the file it is pointed at (UModel.__init__ round-trips the XML back
# to disk, which drops the DOCTYPE line and the <comment> text of every query), so the check
# runs on a copy and battery_sm.xml stays as the translator wrote it.
check = os.path.join(tempfile.mkdtemp(), "battery_sm.xml")
shutil.copyfile(out, check)
m = pyuppaal.UModel(check)
print("pyuppaal.UModel loaded a copy of " + os.path.basename(out))
print("  templates: " + str([t.name for t in m.templates]))
print("  queries:   " + str(len(m.queries)) + " parsed back")
print("  declaration:")
for line in m.declaration.splitlines():
    print("    " + line)
