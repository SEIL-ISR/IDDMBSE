"""The design and the environment against the working files they rewrite.

A design changes `detector.yaml` and an environment changes `scenario.yaml`,
both through PERFECT's `files` updates. The two helpers below are PERFECT's own
rules written out again so that the check runs without a PERFECT installation:

  apply   is perfect/experiment/experiment.py, edit_local_yaml -- walk the dotted
          key, append to a list target, otherwise assign
  fill    is perfect/app/routes/utils.py, fill_specification_kwargs -- replace
          every "$name" by the argument of that name, as a float where it can be

The tests then run the filled files through `calibration_run.settings`, so a
change to either file that the trial cannot read is caught here.
"""

import json
import os

import pytest
import yaml

import calibration_run as cr

HERE = cr.HERE
DETECTORS = {"sharp": -0.6, "nominal": 0.0, "degraded": 1.0}


def apply(contents, updates):
    for update in updates:
        target = contents
        keys = update["keys"].split(".")
        for key in keys[:-1]:
            target = target[key]
        if isinstance(target[keys[-1]], list):
            target[keys[-1]].append(update["value"])
        else:
            target[keys[-1]] = update["value"]
    return contents


def fill(spec, arguments):
    if isinstance(spec, str) and spec.startswith("$"):
        try:
            return float(arguments[spec[1:]])
        except ValueError:
            return arguments[spec[1:]]
    if isinstance(spec, list):
        return [fill(v, arguments) for v in spec]
    if isinstance(spec, dict):
        return {k: fill(v, arguments) for k, v in spec.items()}
    return spec


def library():
    return json.load(open(os.path.join(HERE, "components.json")))


def template():
    return json.load(open(os.path.join(HERE, "environment_template.json")))[0]


def test_the_library_is_three_implementations_of_one_component():
    entries = library()
    assert [c["name"] for c in entries] == list(DETECTORS)
    assert {c["type"] for c in entries} == {"detector"}


@pytest.mark.parametrize("name", list(DETECTORS))
def test_each_design_writes_the_detector_it_is_named_after(name):
    entry = next(c for c in library() if c["name"] == name)
    files = entry["implementation"]["files"]
    assert len(files) == 1 and files[0]["file"] == "detector.yaml"
    assert [u["keys"] for u in files[0]["updates"]] == ["configuration", "shift"]

    written = apply(yaml.safe_load(open(os.path.join(HERE, "detector.yaml"))),
                    files[0]["updates"])
    s = cr.settings(yaml.safe_load(open(os.path.join(HERE, "scenario.yaml"))), written)
    assert s["detector"] == name
    assert s["shift"] == DETECTORS[name]


def test_the_shipped_defaults_are_the_nominal_detector():
    shipped = yaml.safe_load(open(os.path.join(HERE, "detector.yaml")))
    nominal = next(c for c in library() if c["name"] == "nominal")
    assert shipped == apply(dict(shipped), nominal["implementation"]["files"][0]["updates"])


def test_the_environment_writes_the_three_scenario_arguments():
    spec = template()["specification"]
    assert [f["file"] for f in spec["files"]] == ["scenario.yaml"]
    keys = [u["keys"] for u in spec["files"][0]["updates"]]
    assert keys == ["clutter", "seed", "n_episodes"]

    filled = fill(spec, {"clutter": "sparse", "seed": 7, "n_episodes": 2})
    written = apply(yaml.safe_load(open(os.path.join(HERE, "scenario.yaml"))),
                    filled["files"][0]["updates"])
    s = cr.settings(written, yaml.safe_load(open(os.path.join(HERE, "detector.yaml"))))
    assert s["clutter"] == "sparse"
    assert s["band"] == (3, 5)
    assert s["seed"] == 7
    assert s["n_episodes"] == 2


def test_the_scenario_carries_the_three_clutter_bands_and_the_base_seed():
    scenario = yaml.safe_load(open(os.path.join(HERE, "scenario.yaml")))
    assert sorted(scenario["bands"]) == ["dense", "nominal", "sparse"]
    for band in scenario["bands"].values():
        assert len(band) == 2 and band[0] <= band[1]
    assert scenario["frame_every"] >= 1
    assert isinstance(scenario["base_seed"], int)
