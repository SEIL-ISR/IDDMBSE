import importlib.util
import pathlib
import subprocess
import sys

import numpy as np
import pytest

DEMOS = pathlib.Path(__file__).resolve().parents[1]
ANIMATIONS = DEMOS / "animations"
sys.path.insert(0, str(ANIMATIONS))

import render  # noqa: E402


def module(name):
    spec = importlib.util.spec_from_file_location(name + "_make", ANIMATIONS / name / "make.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def quick_render(name, out):
    """Run make.py with four frames; return (stdout, mp4 path)."""
    p = subprocess.run([sys.executable, str(ANIMATIONS / name / "make.py"), "--frames", "4",
                        "--out", str(out)], capture_output=True, text=True)
    assert p.returncode == 0, p.stderr
    assert "frames: 4" in p.stdout
    assert (out / (name + "_poster.svg")).stat().st_size > 10000
    assert (out / (name + "_poster.pdf")).exists()
    assert (out / (name + ".gif")).exists()
    return p.stdout, out / (name + ".mp4")


def not_blank(mp4, index=1):
    f = render.frame_array(mp4, index).astype(float)
    ink = (f.mean(axis=2) < 200).mean()
    return f.std() > 10.0 and ink > 0.02


@pytest.fixture
def check_render(tmp_path):
    def run(name):
        stdout, mp4 = quick_render(name, tmp_path)
        assert not_blank(mp4, 1)
        assert not_blank(mp4, 3)
        return stdout
    return run
