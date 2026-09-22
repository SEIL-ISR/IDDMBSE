"""The UPPAAL model reader and dot layout behind formal/animations, and the script itself."""

import json
import subprocess
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / "formal" / "animations"))

from nta_layout import dot_layout, read_nta  # noqa: E402


def demo_model(tmp_path):
    out = tmp_path / "BT_converted.xml"
    demo = root / "formal" / "bt2automata" / "demo.py"
    subprocess.run([sys.executable, str(demo), str(out)], check=True, capture_output=True)
    return read_nta(out)


def test_the_demo_network_is_read_template_by_template(tmp_path):
    nta = demo_model(tmp_path)
    shape = [(t["name"], len(t["locations"]), len(t["edges"])) for t in nta["templates"]]
    assert shape == [("BT", 6, 11), ("Battery", 2, 3), ("Grid", 86, 362)]
    assert nta["queries"] == ["E<> spec.Success", "E<> spec.Failure"]
    bt = nta["templates"][0]
    assert sorted(loc["name"] for loc in bt["locations"] if loc["name"]) == ["Failure", "Success"]
    assert sum(loc["urgent"] for loc in bt["locations"]) == 1


def test_dot_places_every_location_and_routes_every_edge(tmp_path):
    bt = demo_model(tmp_path)["templates"][0]
    layout = dot_layout(bt)
    assert set(layout["nodes"]) == {loc["id"] for loc in bt["locations"]}
    assert set(layout["names"]) == {loc["id"] for loc in bt["locations"] if loc["name"]}
    assert len(layout["edges"]) == len(bt["edges"])
    ends = sorted((s, t) for s, t, *_ in layout["edges"])
    assert ends == sorted((e["source"], e["target"]) for e in bt["edges"])
    for _, _, spline, tip, _, _ in layout["edges"]:
        assert spline.shape[1] == 2 and (len(spline) - 1) % 3 == 0
        assert tip is not None


def test_the_recorded_verdicts_belong_to_the_demo_queries(tmp_path):
    recorded = json.loads((root / "formal" / "animations" / "uppaal_verdicts.json").read_text())
    assert [f for f, _ in recorded["bt"]] == demo_model(tmp_path)["queries"]
    assert [v for _, v in recorded["bt"]] == ["satisfied", "satisfied"]
    assert len(recorded["sm"]) == 12
    assert recorded["version"].startswith("UPPAAL 5.0.0")


def test_the_animation_script_writes_its_files(tmp_path):
    script = root / "formal" / "animations" / "make_bt_to_automaton.py"
    r = subprocess.run([sys.executable, str(script), "--out", str(tmp_path), "--frames", "4"],
                       capture_output=True, text=True, cwd=root)
    assert r.returncode == 0, r.stderr
    assert "frames 4" in r.stdout
    for name in ["bt_to_automaton.mp4", "bt_to_automaton.gif", "bt_to_automaton_poster.pdf"]:
        assert (tmp_path / name).stat().st_size > 1000
    svg = (tmp_path / "bt_to_automaton_poster.svg").read_text()
    assert svg.count("<path") > 50
