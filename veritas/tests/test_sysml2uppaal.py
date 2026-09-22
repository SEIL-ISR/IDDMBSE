"""The SysML -> UPPAAL translator on the AGR mk6 model.

The expectations are read off the model itself: one uml:StateMachine
`SMD ee_hv_battery_charge_discharge` with five subvertices and five transitions, a ChangeEvent
body `current_soc<0.6`, two TimeEvents (3600 absolute, 1200 relative), an entry behaviour
`current_soc=0.7`, and 23 sysml:Requirement stereotype applications.
"""

import hashlib
import shutil
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

import pyuppaal
import sysml2uppaal as s2u

root = Path(__file__).resolve().parents[1]
model = root.parent / "sysml" / "models" / "AGR_stack-MB-SensorTrade-mk6.mdzip"

aliases = {"current_soc": ["state of charge"], "gt": ["complete the entire path"]}

pytestmark = pytest.mark.skipif(not model.is_file(), reason="the mk6 SysML model is not present")


@pytest.fixture(scope="module")
def translated(tmp_path_factory):
    out = tmp_path_factory.mktemp("nta") / "battery_sm.xml"
    before = hashlib.md5(model.read_bytes()).hexdigest()
    templates, queries, warnings = s2u.translate(
        str(model), str(out), scale=100, aliases=aliases,
        state_machines=["ee_hv_battery_charge_discharge"], activities=["Demo AD"])
    assert hashlib.md5(model.read_bytes()).hexdigest() == before, "the source model was modified"
    return out, templates, queries, warnings


def test_expression_fragment():
    warn = []
    assert s2u.translate_expr("current_soc<0.6", 100, warn, "x")[0] == "current_soc < 60"
    assert s2u.translate_expr("current_soc=0.7", 100, warn, "x")[0] == "current_soc == 70"
    assert s2u.translate_expr("current_soc=0.7", 100, warn, "x", assignment=True)[0] == "current_soc = 70"
    assert s2u.translate_expr("a>=1 && b<2", 1, warn, "x")[0] == "a >= 1 && b < 2"
    assert warn == []

    # outside the fragment: nothing translated, one warning naming the term
    out, bad = s2u.translate_expr("speed*2 < 3", 1, warn, "guard on E")
    assert out is None and bad == ["speed*2 < 3"]
    assert len(warn) == 1 and "cannot translate" in warn[0]

    # a constant that does not survive the scaling is rounded, with a warning
    warn = []
    assert s2u.translate_expr("x < 0.005", 100, warn, "x")[0] == "x < 0"
    assert "not integral at scale 100" in warn[0]


def test_requirements_are_read():
    reqs = s2u.requirements(s2u.load_model(str(model)))
    assert len(reqs) == 23
    by_id = {r["id"]: r for r in reqs}
    assert by_id["P.1.4"]["name"] == "AGR Battery State of Charge"
    assert by_id["P.1.4"]["text"] == (
        "The AGR Battery State of Charge during operation shall always be more than 0.6.")
    assert by_id["P.1.2"]["text"].endswith("in less than 180 seconds.")


def test_state_machine_template(translated):
    _, templates, _, _ = translated
    sm = templates[0]
    assert sm["kind"] == "state machine"
    assert sm["name"] == "ee_hv_battery_charge_discharge"
    names = [loc["name"] for loc in sm["locations"]]
    assert names == ["Pseudostate", "Operational", "Enter_Power_Saving_Mode",
                     "Charging", "Quick_Charge_Complete"]
    assert sm["variables"] == {"current_soc"}

    by_name = {loc["id"]: loc["name"] for loc in sm["locations"]}
    edges = {(by_name[e["source"]], by_name[e["target"]]): e for e in sm["edges"]}
    assert len(edges) == 5

    # the ChangeEvent body current_soc<0.6, scaled by 100
    assert edges[("Operational", "Enter_Power_Saving_Mode")]["guard"] == "current_soc < 60"
    # the TimeEvent without isRelative is an absolute bound on the shared clock
    assert edges[("Enter_Power_Saving_Mode", "Charging")]["guard"] == "gt >= 3600"
    # the TimeEvent with isRelative='true' is after(1200) on the local clock, with the invariant
    assert edges[("Charging", "Quick_Charge_Complete")]["guard"] == "t >= 1200"
    assert [loc["invariant"] for loc in sm["locations"] if loc["name"] == "Charging"] == ["t <= 1200"]
    # the entry behaviour of Operational assigns on every edge entering it
    assert "current_soc = 70" in edges[("Pseudostate", "Operational")]["assignment"]
    assert edges[("Pseudostate", "Operational")]["guard"] is None


def test_activity_template(translated):
    _, templates, _, _ = translated
    act = templates[1]
    assert act["kind"] == "activity" and act["name"] == "Demo_AD"
    assert len(act["locations"]) == 4 and len(act["edges"]) == 4
    assert act["locations"][0]["comment"] == "uml:InitialNode"


def test_queries_from_requirements(translated):
    _, _, queries, _ = translated
    formulas = [q["formula"] for q in queries]
    # the two proof obligations the alias table binds
    assert "A[] current_soc > 60" in formulas
    assert "A[] gt < 180" in formulas
    assert "A[] not deadlock" in formulas
    # one reachability query per location of every template
    assert "E<> ee_hv_battery_charge_discharge_p.Quick_Charge_Complete" in formulas
    assert len(formulas) == 3 + 5 + 4
    soc = next(q for q in queries if q["formula"] == "A[] current_soc > 60")
    assert soc["comment"].startswith("P.1.4 AGR Battery State of Charge:")


def test_warnings_name_what_was_not_translated(translated):
    _, _, _, warnings = translated
    joined = "\n".join(warnings)
    assert "no kind attribute" in joined                      # the unnamed initial Pseudostate
    assert "doActivity of Quick_Charge_Complete" in joined     # do-behaviour applied on entry
    assert "no isRelative attribute" in joined                 # the 3600 TimeEvent
    assert "when (current_soc=0.7) && after(100)" in joined    # the informal transition label
    assert len(warnings) == 4


def test_nta_is_well_formed_and_loads_in_pyuppaal(translated, tmp_path):
    out, templates, queries, _ = translated
    nta = ET.parse(out).getroot()
    assert nta.tag == "nta"
    assert [t.find("name").text for t in nta.findall("template")] == [t["name"] for t in templates]
    assert [q.find("formula").text for q in nta.find("queries").findall("query")] == \
        [q["formula"] for q in queries]
    assert "int current_soc = 70;" in nta.find("declaration").text
    assert "clock gt;" in nta.find("declaration").text

    # every location id is the idN form UPPAAL writes, and every edge endpoint resolves
    ids = {loc.get("id") for t in nta.findall("template") for loc in t.findall("location")}
    assert all(i.startswith("id") and i[2:].isdigit() for i in ids)
    for t in nta.findall("template"):
        local = {loc.get("id") for loc in t.findall("location")}
        assert t.find("init").get("ref") in local
        for tr in t.findall("transition"):
            assert tr.find("source").get("ref") in local
            assert tr.find("target").get("ref") in local

    # pyuppaal 1.2.0 rewrites the file it opens, so the check runs on a copy
    copy = tmp_path / "copy.xml"
    shutil.copyfile(out, copy)
    m = pyuppaal.UModel(str(copy))
    assert [t.name for t in m.templates] == [t["name"] for t in templates]
    assert len(m.queries) == len(queries)
