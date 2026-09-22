"""The sensor catalogue this example offers PERFECT as component implementations.

Thirteen sensors in four families: two 3-D lidars in two configurations each,
two 2-D laser scanners in two configurations each, three depth cameras and two
RGB cameras. The numbers are the ones the model-based stage of TRADES-X uses
(`trades-x/tradesx/sensitivity.py`, itself a port of `trades-x/mbo/src/util_data.jl`):
update rate, horizontal field of view, maximum range, price, electrical power and
the RAM a five-second buffer of the sensor's stream takes. `cost`, `power` and
`ram` here are per-sensor values that add up, over a suite, to exactly what
`tradesx.sensitivity.cost/power/ram` return for the same 13-slot selection
vector; `perfect/examples/sensor-suite-sim/tests/test_catalogue.py` checks that.

`ares` is the horizontal angular resolution in radians, derived from the same
source data: 2*pi divided by the samples per revolution for the lidars, the
field of view divided by the samples per scan for the laser scanners, and the
field of view divided by the image width for the cameras. It is what makes one
sensor see a rock further away than another, so it is the parameter the
simulation leans on hardest.

`light_sensitive` marks the sensors whose performance the scenario's visibility
parameter scales: the depth cameras and the RGB cameras. Lidar and laser
scanners carry their own illumination, so visibility does not touch them.

`type` is the PERFECT component type. The four values are the ones the SysML
bridge endpoint POST /api/v1/run matches on, so a bridge request naming
`{"laser_3d": {"model": "vlp16", "update_rate": 15}}` resolves against this
library.

Running this file rewrites components.json:

    python catalogue.py
"""

import json
import os

SENSORS = [
    {"name": "VLP-16-A", "type": "laser_3d", "kind": "lidar",
     "update_rate": 15.0, "h_fov": 6.283185, "ares": 0.00335103, "max_range": 100.0,
     "cost": 10000.0, "power": 80.000001, "ram": 33.75, "light_sensitive": 0},
    {"name": "VLP-16-B", "type": "laser_3d", "kind": "lidar",
     "update_rate": 20.0, "h_fov": 6.283185, "ares": 0.00335103, "max_range": 100.0,
     "cost": 12000.0, "power": 80.000001, "ram": 60.0, "light_sensitive": 0},
    {"name": "HDL-32E-A", "type": "laser_3d", "kind": "lidar",
     "update_rate": 15.0, "h_fov": 6.283185, "ares": 0.00287297, "max_range": 120.0,
     "cost": 15000.0, "power": 100.000002, "ram": 78.732, "light_sensitive": 0},
    {"name": "HDL-32E-B", "type": "laser_3d", "kind": "lidar",
     "update_rate": 20.0, "h_fov": 6.283185, "ares": 0.00287297, "max_range": 120.0,
     "cost": 16000.0, "power": 100.000003, "ram": 139.968, "light_sensitive": 0},
    {"name": "LMS111-a2", "type": "laser_2d", "kind": "laser",
     "update_rate": 25.0, "h_fov": 4.71, "ares": 0.00654167, "max_range": 20.0,
     "cost": 1000.0, "power": 30.0, "ram": 4.5, "light_sensitive": 0},
    {"name": "LMS111-b1", "type": "laser_2d", "kind": "laser",
     "update_rate": 50.0, "h_fov": 4.71, "ares": 0.00654167, "max_range": 20.0,
     "cost": 1500.0, "power": 30.0, "ram": 18.0, "light_sensitive": 0},
    {"name": "LMS151-a2", "type": "laser_2d", "kind": "laser",
     "update_rate": 25.0, "h_fov": 4.71, "ares": 0.00654167, "max_range": 50.0,
     "cost": 1500.0, "power": 50.0, "ram": 4.5, "light_sensitive": 0},
    {"name": "LMS151-b2", "type": "laser_2d", "kind": "laser",
     "update_rate": 50.0, "h_fov": 4.71, "ares": 0.00654167, "max_range": 50.0,
     "cost": 2000.0, "power": 50.0, "ram": 18.0, "light_sensitive": 0},
    {"name": "D415", "type": "depth_camera", "kind": "depth",
     "update_rate": 60.0, "h_fov": 1.1345, "ares": 0.00210093, "max_range": 6.0,
     "cost": 2000.0, "power": 8.000024, "ram": 3499.2, "light_sensitive": 1},
    {"name": "D435", "type": "depth_camera", "kind": "depth",
     "update_rate": 30.0, "h_fov": 1.5184, "ares": 0.00118625, "max_range": 6.0,
     "cost": 2500.0, "power": 8.000057, "ram": 4147.2, "light_sensitive": 1},
    {"name": "D455", "type": "depth_camera", "kind": "depth",
     "update_rate": 15.0, "h_fov": 1.501, "ares": 0.00078177, "max_range": 6.0,
     "cost": 3000.0, "power": 10.000064, "ram": 2332.8, "light_sensitive": 1},
    {"name": "Blackfly-A", "type": "camera", "kind": "camera",
     "update_rate": 30.0, "h_fov": 1.047, "ares": 0.00145417, "max_range": 50.0,
     "cost": 1500.0, "power": 3.000048, "ram": 3499.2, "light_sensitive": 1},
    {"name": "Blackfly-B", "type": "camera", "kind": "camera",
     "update_rate": 15.0, "h_fov": 1.047, "ares": 0.00067987, "max_range": 60.0,
     "cost": 3000.0, "power": 6.000103, "ram": 3742.2, "light_sensitive": 1},
]

# The keys of a suite entry in sensors.yaml, in the order they are written.
SUITE_KEYS = ("name", "kind", "update_rate", "h_fov", "ares", "max_range",
              "cost", "power", "ram", "light_sensitive")


def component(sensor):
    """One PERFECT component implementation: it appends itself to sensors.yaml.

    `suite` in the default sensors.yaml is an empty list, and PERFECT's
    edit_local_yaml appends a non-list value to a list target, so a design over
    N of these sensors leaves N entries in the working file and the simulation
    reads its whole suite from there.
    """
    entry = {k: sensor[k] for k in SUITE_KEYS}
    return {
        "name": sensor["name"],
        "type": sensor["type"],
        "implementation": {
            "files": [{"file": "sensors.yaml",
                       "updates": [{"keys": "suite", "value": entry}]}],
        },
    }


def components():
    return [component(s) for s in SENSORS]


if __name__ == "__main__":
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "components.json")
    with open(path, "w") as f:
        json.dump(components(), f, indent=4)
        f.write("\n")
    print("wrote", len(SENSORS), "component implementations to components.json")
