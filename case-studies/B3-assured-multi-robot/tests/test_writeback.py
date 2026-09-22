"""The write-back into the AGR fleet model, and the ROS path export."""

import shutil

import numpy as np
import yaml

from assured_ma import ros_export, writeback


def test_goal_satisfaction_round_trips(tmp_path):
    src = "model/agr_fleet.yaml"
    dst = tmp_path / "agr_fleet.yaml"
    shutil.copy(src, dst)
    verdicts = {"AGR_1": {"rho": 0.1993456, "verdict": "satisfied", "binding": "sep(1,2)@k=9"},
                "AGR_2": {"rho": -0.04211, "verdict": "violated", "binding": "OBS_WALL_MID@k=7"},
                "AGR_3": {"rho": 0.4, "verdict": "satisfied", "binding": "ST_C2@k=18"}}
    writeback.write_model(dst, verdicts)
    back = writeback.read_goal_satisfaction(dst)
    assert back == {"AGR_1": 0.199346, "AGR_2": -0.042110, "AGR_3": 0.4}

    doc = yaml.safe_load(dst.read_text())
    blocks = {b["id"]: b for b in doc["blocks"]}
    assert blocks["AGR_2"]["verdict"] == "violated"
    assert blocks["AGR_2"]["binding_conjunct"] == "OBS_WALL_MID@k=7"
    assert blocks["AGR_Fleet_Assembly"]["parts"] == ["AGR_1", "AGR_2", "AGR_3"]
    assert dst.read_text().startswith("#")
    reqs = {r["id"]: r for r in doc["requirements"]}
    assert reqs["M-AGR-2"]["satisfied_by"] == "AGR_2"


def test_path_export_has_the_ros_field_layout(tmp_path):
    traj = np.array([[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [1.0, 1.0]])
    out = tmp_path / "p.yaml"
    ros_export.write_path(out, traj, dt=0.5, frame_id="map", comment="test")
    msg = yaml.safe_load(out.read_text())
    assert set(msg) == {"header", "poses"}
    assert msg["header"]["frame_id"] == "map"
    assert len(msg["poses"]) == 4
    p0 = msg["poses"][1]
    assert set(p0["pose"]) == {"position", "orientation"}
    assert set(p0["pose"]["position"]) == {"x", "y", "z"}
    assert set(p0["pose"]["orientation"]) == {"x", "y", "z", "w"}
    assert p0["header"]["stamp"] == {"sec": 0, "nanosec": 500000000}
    assert msg["poses"][3]["header"]["stamp"] == {"sec": 1, "nanosec": 500000000}

    yaw = [2.0 * np.arctan2(q["pose"]["orientation"]["z"], q["pose"]["orientation"]["w"])
           for q in msg["poses"]]
    assert yaw[0] == np.float64(0.0)                 # first segment points along +x
    assert yaw[1] == np.float64(np.pi / 2)           # second turns to +y
    assert yaw[3] == yaw[2]                          # the last pose holds its heading
