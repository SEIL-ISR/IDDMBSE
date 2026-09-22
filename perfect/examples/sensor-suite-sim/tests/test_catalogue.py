"""The catalogue against the model-based oracles it has to agree with.

TRADES-X's model-based stage prices a design with `tradesx.sensitivity`, whose
numbers come from `trades-x/mbo/src/util_data.jl`. This example serves the same
13 sensors to PERFECT as component implementations, so a suite's totals here
have to be the same numbers. The reference triples below were read off
`tradesx.sensitivity.cost/ram/power` for the designs the study carries; this
file checks the catalogue reproduces them by plain addition.
"""

import json
import os

import pytest

import catalogue

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# design id -> (sensor names, cost, ram, power) from tradesx.sensitivity
REFERENCE = {
    4234: (["VLP-16-A", "LMS111-b1", "D435", "Blackfly-A"], 15500.0, 7698.15, 121.0001058747382),
    785: (["HDL-32E-B", "LMS111-a2", "D415", "Blackfly-B"], 22000.0, 7385.868, 144.00012951281852),
    549: (["HDL-32E-B", "LMS151-b2", "D455", "Blackfly-B"], 24000.0, 6232.968, 166.00016955352692),
    2185: (["VLP-16-B", "LMS111-b1", "D435", "Blackfly-B"], 19000.0, 7967.4, 124.0001608042744),
    4370: (["VLP-16-A", "LMS111-a2", "D415", "Blackfly-A"], 14500.0, 7036.65, 121.0000729392202),
    4: (["D455"], 3000.0, 2332.7999999999997, 10.0000639467136),
    512: (["HDL-32E-B"], 16000.0, 139.96800000000002, 100.00000287760211),
}


def by_name():
    return {s["name"]: s for s in catalogue.SENSORS}


@pytest.mark.parametrize("design_id", sorted(REFERENCE))
def test_suite_totals_match_the_model_based_oracles(design_id):
    names, cost, ram, power = REFERENCE[design_id]
    table = by_name()
    assert sum(table[n]["cost"] for n in names) == pytest.approx(cost)
    assert sum(table[n]["ram"] for n in names) == pytest.approx(ram, rel=1e-9)
    assert sum(table[n]["power"] for n in names) == pytest.approx(power, rel=1e-8)


def test_thirteen_sensors_with_unique_names():
    assert len(catalogue.SENSORS) == 13
    assert len({s["name"] for s in catalogue.SENSORS}) == 13


def test_every_component_carries_one_suite_append():
    for s in catalogue.SENSORS:
        c = catalogue.component(s)
        assert c["type"] in ("laser_3d", "laser_2d", "depth_camera", "camera")
        files = c["implementation"]["files"]
        assert len(files) == 1 and files[0]["file"] == "sensors.yaml"
        updates = files[0]["updates"]
        assert len(updates) == 1 and updates[0]["keys"] == "suite"
        assert set(updates[0]["value"]) == set(catalogue.SUITE_KEYS)


def test_only_cameras_and_depth_cameras_are_light_sensitive():
    for s in catalogue.SENSORS:
        assert s["light_sensitive"] == int(s["kind"] in ("camera", "depth"))


def test_components_json_is_what_catalogue_generates():
    on_disk = json.load(open(os.path.join(HERE, "components.json")))
    assert on_disk == catalogue.components()
