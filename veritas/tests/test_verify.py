"""The model-checker driver: query extraction, verdict parsing and the report.

No UPPAAL is needed: `fake_verifyta.py` writes the same shape of output, so extraction,
invocation, parsing and the report are exercised end to end.  The parser is additionally
checked against a block of real verifyta output.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

import verify

root = Path(__file__).resolve().parents[1]
stub = Path(__file__).resolve().parent / "fake_verifyta.py"

MODEL = """<?xml version='1.0' encoding='utf-8'?>
<!DOCTYPE nta PUBLIC '-//Uppaal Team//DTD Flat System 1.1//EN' 'http://www.it.uu.se/research/group/darts/uppaal/flat-1_1.dtd'>
<nta>
<declaration>int current_soc = 70; clock gt;</declaration>
<template><name>P</name><location id="id0"><name>A</name></location><init ref="id0"/></template>
<system>p = P(); system p;</system>
<queries>
<query><formula>A[] not deadlock</formula><comment>structural check</comment></query>
<query><formula>A[] gt &lt; 180</formula><comment>P.1.2 Time to Completion:
the AGR shall complete the path in less than 180 seconds</comment></query>
<query><formula>A&lt;&gt; p.A</formula><comment></comment></query>
<query><formula>E&lt;&gt; p.A</formula><comment>reachability of A</comment></query>
</queries>
</nta>
"""

# Output captured from UPPAAL 5.0.0 on this repository's own battery model, kept verbatim
# including the erase-line escape its progress indicator leaves in front of each verdict.
CAPTURED_5 = ("Options for the verification:\n"
              "  Generating some trace\n"
              "  Search order is breadth first\n"
              "  Using conservative space optimisation\n"
              "  Seed is 1790094736\n"
              "  State space representation uses minimal constraint systems with future testing\n"
              "  Using HashMap + Compress integers for discrete state storage\n"
              "\x1b[2K\n"
              "Verifying formula 1 at formal/sysml2uppaal/battery_sm.q:2\n"
              "\x1b[2K -- Formula is NOT satisfied.\n"
              " -- Showing witness trace:\n"
              "\nState:\n( ee_hv_battery_charge_discharge_p.Pseudostate demo_ad_p.InitialNode )\n"
              "\x1b[2K\n"
              "Verifying formula 2 at formal/sysml2uppaal/battery_sm.q:4\n"
              "\x1b[2K -- Formula is satisfied.\n")

# The same shape from UPPAAL 4.1, reproduced in the comment block of pyuppaal's own wrapper
# (`pyuppaal/verifyta.py`, the `Showing` branch of `Verifyta.cmd`): the query index is the
# path into the model's queries block there, and no escape sequence precedes the verdict.
# The `MAY be satisfied` line is written by analogy with the other two.
CAPTURED_41 = """Options for the verification:
  Generating shortest trace
  Search order is breadth first

Verifying formula 1 at /nta/queries/query[1]/formula
 -- Formula is NOT satisfied.
Showing counter example.
Verifying formula 2 at /nta/queries/query[2]/formula
 -- Formula is satisfied.
Verifying formula 3 at /nta/queries/query[3]/formula
 -- Formula MAY be satisfied.
"""


@pytest.fixture
def model(tmp_path):
    p = tmp_path / "toy.xml"
    p.write_text(MODEL)
    return p


def test_queries_come_out_of_the_model_in_order(model):
    qs = verify.read_queries(str(model))
    assert [q["index"] for q in qs] == [1, 2, 3, 4]
    assert [q["formula"] for q in qs] == ["A[] not deadlock", "A[] gt < 180", "A<> p.A", "E<> p.A"]
    assert qs[1]["comment"].startswith("P.1.2 Time to Completion")
    assert qs[2]["comment"] == ""


def test_the_query_file_is_one_formula_per_line_with_comments(model, tmp_path):
    q = tmp_path / "toy.q"
    verify.write_query_file(verify.read_queries(str(model)), str(q))
    lines = q.read_text().splitlines()
    assert lines[0] == "// structural check"
    assert lines[1] == "A[] not deadlock"
    # a two-line comment becomes two // lines
    assert lines[2] == "// P.1.2 Time to Completion:"
    assert lines[3] == "// the AGR shall complete the path in less than 180 seconds"
    assert lines[4] == "A[] gt < 180"
    assert [ln for ln in lines if not ln.startswith("//")] == [
        "A[] not deadlock", "A[] gt < 180", "A<> p.A", "E<> p.A"]


def test_the_parser_reads_captured_uppaal_5_output():
    assert verify.parse_verdicts(CAPTURED_5) == [(1, "not satisfied"), (2, "satisfied")]


def test_the_parser_reads_the_uppaal_4_shape():
    assert verify.parse_verdicts(CAPTURED_41) == [
        (1, "not satisfied"), (2, "satisfied"), (3, "may be satisfied")]


def test_the_parser_falls_back_on_output_order():
    # some builds print no `Verifying formula N` line; the verdicts still arrive in query order
    text = " -- Formula is satisfied.\n -- Formula is NOT satisfied.\n"
    assert verify.parse_verdicts(text) == [(1, "satisfied"), (2, "not satisfied")]


def test_verifyta_is_looked_up_in_uppaal_home_before_path(tmp_path, monkeypatch):
    home = tmp_path / "uppaal"
    (home / "bin-Linux").mkdir(parents=True)
    exe = home / "bin-Linux" / "verifyta"
    exe.write_text("#!/bin/sh\n")
    exe.chmod(0o755)
    monkeypatch.setenv("UPPAAL_HOME", str(home))
    assert verify.find_verifyta() == str(exe)

    monkeypatch.delenv("UPPAAL_HOME")
    monkeypatch.setenv("PATH", "")
    assert verify.find_verifyta() is None
    # an explicit path always wins
    assert verify.find_verifyta(str(exe)) == str(exe)


def run_driver(args, cwd, env=None):
    e = dict(os.environ)
    e.pop("PYTHONPATH", None)
    if env:
        e.update(env)
    return subprocess.run([sys.executable, str(root / "formal" / "verify.py")] + args,
                          capture_output=True, text=True, cwd=str(cwd), env=e)


def test_end_to_end_against_the_stub(model, tmp_path):
    r = run_driver(["--verifyta", str(stub), str(model)], tmp_path)
    assert r.returncode == 0, r.stderr

    report = json.loads((tmp_path / "verification_report.json").read_text())
    assert report["verifyta"] == str(stub)
    qs = report["models"][0]["queries"]
    # the stub's rule: deadlock satisfied, the 180 s bound not satisfied, A<> may be, E<> satisfied
    assert [q["verdict"] for q in qs] == [
        "satisfied", "not satisfied", "may be satisfied", "satisfied"]
    assert qs[1]["comment"].startswith("P.1.2")
    assert report["models"][0]["seconds"] > 0

    md = (tmp_path / "verification_report.md").read_text()
    assert "| 2 | `A[] gt < 180` |" in md
    assert "not satisfied" in md
    # the query file was written next to the model
    assert (model.parent / "toy.q").is_file()


def test_the_generated_behavior_tree_model_is_checked(tmp_path):
    out = tmp_path / "BT_converted.xml"
    demo = subprocess.run([sys.executable, str(root / "formal" / "bt2automata" / "demo.py"),
                           str(out)], capture_output=True, text=True)
    assert demo.returncode == 0, demo.stderr
    r = run_driver(["--verifyta", str(stub), str(out)], tmp_path)
    assert r.returncode == 0, r.stderr
    qs = json.loads((tmp_path / "verification_report.json").read_text())["models"][0]["queries"]
    assert [q["formula"] for q in qs] == ["E<> spec.Success", "E<> spec.Failure"]
    assert [q["verdict"] for q in qs] == ["satisfied", "satisfied"]


@pytest.mark.skipif(verify.find_verifyta() is None,
                    reason="no verifyta on this machine (set UPPAAL_HOME to run this)")
def test_a_real_verifyta_checks_the_generated_model(tmp_path):
    """With an UPPAAL installed, the same driver run gives real verdicts."""
    out = tmp_path / "BT_converted.xml"
    demo = subprocess.run([sys.executable, str(root / "formal" / "bt2automata" / "demo.py"),
                           str(out)], capture_output=True, text=True)
    assert demo.returncode == 0, demo.stderr
    r = run_driver([str(out)], tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr
    report = json.loads((tmp_path / "verification_report.json").read_text())
    assert "UPPAAL" in report["version"]
    verdicts = [q["verdict"] for q in report["models"][0]["queries"]]
    assert verdicts == ["satisfied", "satisfied"]


def test_without_a_verifyta_it_says_so_in_one_line_and_exits_2(model, tmp_path):
    r = run_driver([str(model)], tmp_path, env={"PATH": "", "UPPAAL_HOME": ""})
    assert r.returncode == 2
    assert r.stdout.strip().splitlines() == [
        "set UPPAAL_HOME to an UPPAAL installation, or pass --verifyta <path to verifyta>"]
    assert not (tmp_path / "verification_report.json").exists()
