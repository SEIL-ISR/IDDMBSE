"""The bt2automata demo composes the example BT and writes a well-formed UPPAAL NTA."""

import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

root = Path(__file__).resolve().parents[1]
demo = root / "formal" / "bt2automata" / "demo.py"


def test_demo_writes_nta(tmp_path):
    out = tmp_path / "BT_converted.xml"
    r = subprocess.run([sys.executable, str(demo), str(out)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert out.is_file()

    nta = ET.parse(out).getroot()
    assert nta.tag == "nta"

    # the composed root BT plus the two environment automata copied over unchanged
    names = [t.find("name").text for t in nta.findall("template")]
    assert names == ["BT", "Battery", "Grid"]

    # both queries from the paper: a satisfying trace exists, and a violating one does too
    queries = [q.find("formula").text for q in nta.find("queries").findall("query")]
    assert queries == ["E<> spec.Success", "E<> spec.Failure"]

    # the BT template must expose the two verdict locations the queries name
    bt = nta.findall("template")[0]
    locations = {loc.find("name").text for loc in bt.findall("location") if loc.find("name") is not None}
    assert {"Success", "Failure"} <= locations

    # spec=BT(20) in the system declaration needs the template to take the horizon parameter
    assert bt.find("parameter").text == "const int T"
    assert "spec=BT(20)" in nta.find("system").text
