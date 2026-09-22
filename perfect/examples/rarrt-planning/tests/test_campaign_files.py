"""The design and the environment against the working files they rewrite.

A design changes `policy.yaml` and an environment changes `scenario.yaml`, both
through PERFECT's `files` updates. The two helpers below are PERFECT's own rules
written out again so that the check runs without a PERFECT installation:

  apply   is perfect/experiment/experiment.py, edit_local_yaml -- walk the dotted
          key, append to a list target, otherwise assign
  fill    is perfect/app/routes/utils.py, fill_specification_kwargs -- replace
          every "$name" by the argument of that name, as a float where it can be

The tests then run the filled files through `planner_trial.settings`, so a change
to either file that the trial cannot read is caught here.
"""

import json
import os

import pytest
import yaml

import planner_trial as pt

HERE = pt.HERE
POLICIES = {"rrtstar": ("euclidean", None), "neutral": ("cvar", 0.0),
            "cvar0.1": ("cvar", 0.1), "cvar0.5": ("cvar", 0.5), "cvar0.9": ("cvar", 0.9)}


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


def test_the_library_is_five_implementations_of_one_component():
    entries = library()
    assert [c["name"] for c in entries] == list(POLICIES)
    assert {c["type"] for c in entries} == {"planner"}


@pytest.mark.parametrize("name", list(POLICIES))
def test_each_design_writes_the_policy_it_is_named_after(name):
    entry = next(c for c in library() if c["name"] == name)
    files = entry["implementation"]["files"]
    assert len(files) == 1 and files[0]["file"] == "policy.yaml"
    assert [u["keys"] for u in files[0]["updates"]] == ["policy", "risk", "alpha"]

    written = apply(yaml.safe_load(open(os.path.join(HERE, "policy.yaml"))),
                    files[0]["updates"])
    assert written["policy"] == name
    risk, alpha = POLICIES[name]
    assert written["risk"] == risk
    settings = pt.settings(yaml.safe_load(open(os.path.join(HERE, "scenario.yaml"))), written)
    assert settings["alpha"] == alpha
    assert settings["policy"] == name


def test_the_shipped_defaults_are_the_first_policy_in_the_library():
    shipped = yaml.safe_load(open(os.path.join(HERE, "policy.yaml")))
    first = library()[0]["implementation"]["files"][0]["updates"]
    assert shipped == apply(dict(shipped), first)


def test_the_environment_writes_the_four_scenario_arguments():
    spec = template()["specification"]
    assert [f["file"] for f in spec["files"]] == ["scenario.yaml"]
    keys = [u["keys"] for u in spec["files"][0]["updates"]]
    assert keys == ["environment", "sigma", "seed", "n_exec"]

    arguments = {"environment": "hard", "sigma": 0.05, "seed": 4, "n_exec": 64}
    filled = fill(spec, arguments)
    written = apply(yaml.safe_load(open(os.path.join(HERE, "scenario.yaml"))),
                    filled["files"][0]["updates"])
    settings = pt.settings(written, yaml.safe_load(open(os.path.join(HERE, "policy.yaml"))))
    assert settings["env"] == "hard"
    assert settings["coverage"] == 0.26
    assert settings["sigma"] == 0.05
    assert settings["seed"] == 4
    assert settings["cfg"]["n_exec"] == 64


def test_the_scenario_carries_every_fixed_setting_the_trial_reads():
    scenario = yaml.safe_load(open(os.path.join(HERE, "scenario.yaml")))
    for key in pt.FIXED + ["environment", "sigma", "seed", "n_exec", "coverages"]:
        assert key in scenario
    assert sorted(scenario["coverages"]) == ["easy", "hard", "medium"]
