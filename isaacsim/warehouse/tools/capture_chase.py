"""Chase-camera capture of the Carter in the running Isaac Sim.

`arm` installs an update hook in Isaac Sim that never plays or stops the
timeline: while the timeline plays it follows the chassis with a smoothed
camera, writes one viewport frame every 1/fps seconds of simulation time, and
records the chassis pose of every frame; it stops after --duration simulation
seconds or on `off`, and writes a manifest. `encode` turns the frames into an
H.264 MP4 and three stills (numpy and ffmpeg; the other commands need only the
standard library).

    python3 tools/capture_chase.py arm --frames /tmp/iddmbse-warehouse/frames --manifest /tmp/iddmbse-warehouse/capture.json
    python3 tools/capture_chase.py status
    python3 tools/capture_chase.py off
    uv run --project ../tools python tools/capture_chase.py encode --out results/warehouse_nav_chase.mp4

Adapted from the chase-capture script of the authors' C-BASE workspace (2026).
"""

import argparse
import json
import shutil
import subprocess
from pathlib import Path

from py_server_client import run

CHASSIS = "/World/Nova_Carter_ROS/chassis_link"

ARM = """
import json, math, os, time
import numpy as np
import omni.kit.app, omni.timeline, omni.usd
from pxr import Usd, UsdGeom
from omni.kit.viewport.utility import get_active_viewport, capture_viewport_to_file
from isaacsim.core.rendering_manager import ViewportManager

state = globals().setdefault("_IDDMBSE_CHASE", {})
if state.get("sub") is not None:
    raise RuntimeError("chase capture is already armed")
vp = get_active_viewport()
stage = omni.usd.get_context().get_stage()
if vp is None or not stage.GetPrimAtPath(%(chassis)r).IsValid():
    raise RuntimeError("viewport or Carter chassis is unavailable")
vp.camera_path = "/OmniverseKit_Persp"
os.makedirs(%(frames)r, exist_ok=False)
capacity = int(%(fps)r * %(duration)r) + 8
state.clear()
state.update(sub=None, frames=%(frames)r, manifest=%(manifest)r, fps=float(%(fps)r), duration=float(%(duration)r),
             mode=%(mode)r, n=0, start=None, next_time=None, rows=np.zeros((capacity, 13)), error=None,
             chassis=%(chassis)r, viewport_resolution=list(vp.resolution), eye=None, target=None, done=False, stop_reason=None)
timeline = omni.timeline.get_timeline_interface()
OFFSETS = {"chase": ((-3.4, 0.0, 1.9), (1.2, 0.0, 0.35)), "high": ((-4.5, -3.0, 4.2), (1.0, 0.0, 0.3)), "top": ((0.0, 0.0, 14.0), (0.0, 0.0, 0.0))}

def desired_camera(p, yaw, mode):
    c, s = math.cos(yaw), math.sin(yaw)
    rot = np.array([[c, -s, 0.0], [s, c, 0.0], [0.0, 0.0, 1.0]])
    eye, target = (p + rot @ np.array(v) for v in OFFSETS[mode])
    if mode == "top":
        eye[1] -= 0.001
    return eye, target

def finish(reason):
    st = _IDDMBSE_CHASE
    st["sub"] = None
    st["done"] = True
    st["stop_reason"] = reason
    n = int(st["n"])
    body = {"schema_version": "iddmbse-chase-capture-v1", "camera_mode": st["mode"], "chassis_prim": st["chassis"], "fps_sim": st["fps"],
            "requested_duration_s": st["duration"], "viewport_resolution": st["viewport_resolution"], "scheduled_frame_count": n,
            "written_frame_count": len([q for q in os.listdir(st["frames"]) if q.endswith(".png")]), "stop_reason": reason,
            "columns": ["frame_index", "sim_time_s", "wall_monotonic_s", "chassis_x_m", "chassis_y_m", "chassis_z_m", "chassis_yaw_rad",
                        "eye_x", "eye_y", "eye_z", "target_x", "target_y", "target_z"],
            "frames": st["rows"][:n].tolist(), "error": st["error"]}
    with open(st["manifest"], "w") as stream:
        json.dump(body, stream, indent=1)

def tick(_event):
    st = _IDDMBSE_CHASE
    if st.get("sub") is None or not timeline.is_playing():
        return
    try:
        sim_time = float(timeline.get_current_time())
        m = UsdGeom.Xformable(omni.usd.get_context().get_stage().GetPrimAtPath(st["chassis"])).ComputeLocalToWorldTransform(Usd.TimeCode.Default())
        p = np.array(m.ExtractTranslation(), dtype=float)
        yaw = math.atan2(m[0][1], m[0][0])
        eye, target = desired_camera(p, yaw, st["mode"])
        if st["eye"] is None:
            st["eye"], st["target"] = eye, target
        else:
            st["eye"] = st["eye"] + 0.1 * (eye - st["eye"])
            st["target"] = st["target"] + 0.1 * (target - st["target"])
        ViewportManager.set_camera_view("/OmniverseKit_Persp", eye=st["eye"].tolist(), target=st["target"].tolist())
        if st["start"] is None:
            st["start"] = sim_time
            st["next_time"] = sim_time
        if sim_time + 1.0e-9 < st["next_time"]:
            return
        n = st["n"]
        if n >= st["rows"].shape[0] or sim_time - st["start"] > st["duration"]:
            finish("duration")
            return
        capture_viewport_to_file(vp, os.path.join(st["frames"], "frame_%%05d.png" %% n))
        st["rows"][n] = np.concatenate([[n, sim_time, time.monotonic()], p, [yaw], st["eye"], st["target"]])
        st["n"] = n + 1
        st["next_time"] = st["start"] + st["n"] / st["fps"]
    except Exception as error:
        st["error"] = repr(error)
        finish("error")

state["sub"] = omni.kit.app.get_app().get_update_event_stream().create_subscription_to_pop(tick, name="iddmbse_chase_capture")
print("ARMED", json.dumps({k: state[k] for k in ("frames", "fps", "duration", "mode", "viewport_resolution")}))
"""

STATUS = """
import json, os
st = globals().get("_IDDMBSE_CHASE", {})
frames = st.get("frames")
count = len([p for p in os.listdir(frames) if p.endswith(".png")]) if frames and os.path.isdir(frames) else 0
print(json.dumps({"armed": st.get("sub") is not None, "done": st.get("done"), "stop_reason": st.get("stop_reason"),
                  "scheduled_frames": st.get("n", 0), "written_frames": count, "start_sim_s": st.get("start"), "error": st.get("error")}))
"""

OFF = """
st = globals().get("_IDDMBSE_CHASE", {})
if st.get("sub") is not None:
    finish("off")
st["sub"] = None
print("OFF", st.get("n", 0))
"""


def encode(frames, manifest, out, seconds):
    """H.264 MP4 at 24 fps from every k-th frame so that it runs about `seconds`, plus three 960 px stills."""
    import numpy as np

    info = json.loads(Path(manifest).read_text())
    files = sorted(Path(frames).glob("frame_*.png"))
    step = max(1, round(len(files) / (seconds * 24)))
    work = Path(frames).parent / "encode"
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir()
    picked = files[::step]
    for i, f in enumerate(picked):
        (work / ("f_" + str(i).zfill(5) + ".png")).symlink_to(f.resolve())
    out = Path(out)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-framerate", "24", "-i", str(work / "f_%05d.png"),
                    "-vf", "scale=1280:-2", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "26", "-movflags", "+faststart",
                    str(out)], check=True)
    stills = {}
    for name, f in zip(("start", "middle", "end"), (files[0], files[len(files) // 2], files[-1])):
        still = out.with_name(out.stem + "_" + name + ".png")
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(f), "-vf", "scale=960:-2", str(still)], check=True)
        stills[still.name] = f.name
    rows = np.asarray(info["frames"])
    path = float(np.hypot(*np.diff(rows[:, 3:5], axis=0).T).sum()) if len(rows) > 1 else 0.0
    summary = {
        "video": out.name, "output_fps": 24, "frames_captured": len(files), "frames_used": len(picked), "frame_step": step,
        "frames_per_timeline_second": info["fps_sim"], "timeline_seconds_per_video_second": step * 24 / info["fps_sim"],
        "timeline_span_s": [round(float(rows[0, 1]), 3), round(float(rows[-1, 1]), 3)] if len(rows) else None,
        "chassis_start_xy_m": rows[0, 3:5].round(3).tolist() if len(rows) else None,
        "chassis_end_xy_m": rows[-1, 3:5].round(3).tolist() if len(rows) else None,
        "chassis_path_m": round(path, 3),
        "stills": stills, "viewport_resolution": info["viewport_resolution"],
        "stop_reason": info["stop_reason"], "camera_mode": info["camera_mode"],
    }
    out.with_name(out.stem + "_manifest.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("command", choices=("arm", "status", "off", "encode"))
    parser.add_argument("--frames", default="/tmp/iddmbse-warehouse/frames")
    parser.add_argument("--manifest", default="/tmp/iddmbse-warehouse/capture.json")
    parser.add_argument("--out", default=str(Path(__file__).resolve().parent.parent / "results" / "warehouse_nav_chase.mp4"))
    parser.add_argument("--fps", type=float, default=8.0, help="frames per second of simulation time")
    parser.add_argument("--duration", type=float, default=600.0, help="simulation seconds before the hook stops itself")
    parser.add_argument("--seconds", type=float, default=30.0, help="length of the encoded video")
    parser.add_argument("--mode", choices=("chase", "high", "top"), default="high")
    args = parser.parse_args()
    if args.command == "arm":
        values = {"chassis": CHASSIS, "frames": args.frames, "manifest": args.manifest, "fps": args.fps,
                  "duration": args.duration, "mode": args.mode}
        print(run(ARM % values).strip())
    elif args.command == "status":
        print(run(STATUS).strip())
    elif args.command == "off":
        print(run(OFF).strip())
    else:
        encode(args.frames, args.manifest, args.out, args.seconds)


if __name__ == "__main__":
    main()
