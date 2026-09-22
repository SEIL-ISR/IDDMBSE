"""What the five animations share: the repository root, the video, GIF and poster writers.

Every animation is a matplotlib figure with a `draw(t)` that puts the figure in the state
of timeline position t in [0, 1]. `render` walks t over the frames, pipes them to ffmpeg
through FFMpegWriter (H.264, yuv420p), turns the MP4 into a palette GIF, and saves the
poster frame as SVG and PDF from the same figure.
"""

import argparse
import pathlib
import subprocess
import time

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.animation import FFMpegWriter

ROOT = pathlib.Path(__file__).resolve().parents[2]
FFMPEG = "/usr/bin/ffmpeg"

WIDTH, HEIGHT, DPI = 1280, 720, 100

plt.rcParams["animation.ffmpeg_path"] = FFMPEG
# fixed ids and no date stamps, so two renders write the same poster bytes
plt.rcParams["svg.hashsalt"] = "iddmbse-demos"
plt.rcParams["font.size"] = 11


def arguments(name, fps=24):
    p = argparse.ArgumentParser(description="Render the " + name + " animation.")
    p.add_argument("--out", default=str(pathlib.Path(__file__).parent / name),
                   help="output directory")
    p.add_argument("--frames", type=int, default=None,
                   help="render only this many frames spread over the timeline (quick test)")
    p.add_argument("--fps", type=int, default=fps)
    return p.parse_args()


def figure():
    return plt.figure(figsize=(WIDTH / DPI, HEIGHT / DPI), dpi=DPI)


def timeline(n_full, frames=None):
    """Timeline positions in [0, 1] for the frames to render."""
    n = n_full if frames is None else max(2, int(frames))
    return np.linspace(0.0, 1.0, n)


def render(fig, draw, ts, out, name, fps, poster_t=1.0, crf=23, gif_fps=12,
           gif_speed=1.0, gif_span=(0.0, 1.0)):
    out = pathlib.Path(out)
    out.mkdir(parents=True, exist_ok=True)
    mp4 = out / (name + ".mp4")
    gif = out / (name + ".gif")
    start = time.time()

    writer = FFMpegWriter(fps=fps, codec="libx264", bitrate=-1,
                          extra_args=["-pix_fmt", "yuv420p", "-crf", str(crf),
                                      "-preset", "medium", "-threads", "4"])
    with writer.saving(fig, str(mp4), DPI):
        for t in ts:
            draw(t)
            writer.grab_frame()

    make_gif(mp4, gif, gif_fps, gif_speed, gif_span, len(ts) / fps)

    draw(poster_t)
    fig.savefig(out / (name + "_poster.svg"), metadata={"Date": None})
    fig.savefig(out / (name + "_poster.pdf"), metadata={"CreationDate": None, "ModDate": None})
    plt.close(fig)

    wall = time.time() - start
    print("frames:", len(ts))
    print("duration s:", round(len(ts) / fps, 2))
    print("mp4 bytes:", mp4.stat().st_size)
    print("gif bytes:", gif.stat().st_size)
    print("poster:", out / (name + "_poster.svg"))
    print("wall s:", round(wall, 1))
    return mp4


def make_gif(mp4, gif, fps, speed, span, duration):
    """640 px wide palette GIF of the MP4, optionally sped up or cut to a span of it."""
    t0, t1 = span[0] * duration, span[1] * duration
    chain = ("trim=start={}:end={},setpts=(PTS-STARTPTS)/{},fps={},scale=640:-1:flags=lanczos,"
             "split[a][b];[a]palettegen=max_colors=128:stats_mode=diff[p];"
             "[b][p]paletteuse=dither=bayer:bayer_scale=5:diff_mode=rectangle"
             ).format(t0, t1, speed, fps)
    subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-i", str(mp4),
                    "-filter_complex", chain, "-loop", "0", str(gif)], check=True)


def frame_array(mp4, index):
    """One decoded frame of an MP4 as an (H, W, 3) uint8 array."""
    raw = subprocess.run([FFMPEG, "-loglevel", "error", "-i", str(mp4), "-vf",
                          "select=eq(n\\,{})".format(index), "-vframes", "1",
                          "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                         check=True, capture_output=True).stdout
    return np.frombuffer(raw, dtype=np.uint8).reshape(HEIGHT, WIDTH, 3)


def ease(x):
    """Smoothstep on [0, 1], clipped."""
    x = np.clip(x, 0.0, 1.0)
    return x * x * (3.0 - 2.0 * x)
