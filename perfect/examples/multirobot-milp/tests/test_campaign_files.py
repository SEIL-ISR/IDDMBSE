"""The design and the environment against the working files they rewrite.

A design changes `config.yaml` and an environment changes `execution.yaml`, both
through PERFECT's `files` updates. The two helpers below are PERFECT's own rules
written out again so that the check runs without a PERFECT installation:

  apply   is perfect/experiment/experiment.py, edit_local_yaml -- walk the dotted
          key, append to a list target, otherwise assign
  fill    is perfect/app/routes/utils.py, fill_specification_kwargs -- replace
          every "$name" by the argument of that name, as a float where it can be

The filled files then go through `coordination_trial.settings`, so a change to
either file that the trial cannot read is caught here.
"""

import itertools
import json
import os

import pytest
import yaml

import coordination_trial as ct

HERE = ct.HERE
ROBOTS = ["AGR_1", "AGR_2", "AGR_3"]
MARGINS = [0.15, 0.35, 0.45, 0.5]


def apply(contents, updates):
    for update in updates:
        target = contents
        keys = update["keys"].split(".")
        for key in keys[:-1]:
            target = target[key]
        if isinstance(target[keys[-1]], list):
            if isinstance(update["value"], list):
                target[keys[-1]].extend(update["value"])
            else:
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


def shipped(name):
    return yaml.safe_load(open(os.path.join(HERE, name)))


def test_the_library_is_every_allocation_at_every_margin():
    names = [c["name"] for c in library()]
    wanted = ["alloc" + "".join(map(str, p)) + "-m" + str(m)
              for p in itertools.permutations(range(3)) for m in MARGINS]
    assert names == wanted
    assert {c["type"] for c in library()} == {"coordinator"}


@pytest.mark.parametrize("entry", library(), ids=lambda c: c["name"])
def test_each_design_writes_the_configuration_it_is_named_after(entry):
    files = entry["implementation"]["files"]
    assert len(files) == 1 and files[0]["file"] == "config.yaml"
    written = apply(shipped("config.yaml"), files[0]["updates"])
    s = ct.settings(written, shipped("execution.yaml"), ROBOTS)
    perm, margin = entry["name"][5:].split("-m")
    assert s["allocation"] == tuple(int(c) for c in perm)
    assert s["required_margin"] == float(margin)
    assert all(isinstance(written["allocation"][r], int) for r in ROBOTS)


def test_the_shipped_defaults_are_the_model_files_own_design():
    entry = next(c for c in library() if c["name"] == "alloc012-m0.35")
    defaults = shipped("config.yaml")
    assert apply(shipped("config.yaml"), entry["implementation"]["files"][0]["updates"]) == defaults
    assert (defaults["node_limit"], defaults["mip_rel_gap"], defaults["time_limit_s"]) == \
        (8000, 0.05, 240.0)


def test_the_environment_writes_the_disturbance_and_the_seed():
    spec = json.load(open(os.path.join(HERE, "environment_template.json")))[0]["specification"]
    assert [f["file"] for f in spec["files"]] == ["execution.yaml"]
    assert [u["keys"] for u in spec["files"][0]["updates"]] == ["sigma", "seed"]
    filled = fill(spec, {"sigma": 0.12, "seed": 2})
    written = apply(shipped("execution.yaml"), filled["files"][0]["updates"])
    s = ct.settings(shipped("config.yaml"), written, ROBOTS)
    assert s["sigma"] == 0.12
    assert s["seed"] == 2 and isinstance(s["seed"], int)
    assert (s["pole"], s["clip_sigma"]) == (0.8, 3.0)


def test_the_project_config_gives_sqlite_a_minute_for_its_lock():
    import runpy
    cfg = runpy.run_path(os.path.join(HERE, "config.py"))
    assert cfg["SQLALCHEMY_ENGINE_OPTIONS"] == {"connect_args": {"timeout": 60}}
    assert yaml.safe_load(open(os.path.join(HERE, "config.yaml")))["time_limit_s"] < 270
