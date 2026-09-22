#!/usr/bin/env python3
"""Run Python inside a running Isaac Sim through isaacsim.code_editor.python_server.

The code text is executed by Isaac Sim's own interpreter; globals persist between
calls. Standard library only, so any Python runs this client.

    python3 py_server_client.py 'print("hi")'
    echo 'print("hi")' | python3 py_server_client.py

Copied from the authors' C-BASE workspace (2026); the port is 8236 here.
"""

import json
import socket
import sys
import time
from pathlib import Path

HOST, PORT = "127.0.0.1", 8236


def execute(source, host=HOST, port=PORT, timeout=120):
    s = socket.create_connection((host, port), timeout=timeout)
    try:
        s.sendall(source.encode("utf-8"))
        s.shutdown(socket.SHUT_WR)
        buf = b""
        while True:
            chunk = s.recv(65536)
            if not chunk:
                break
            buf += chunk
    finally:
        s.close()
    return json.loads(buf.decode("utf-8"))


def run(source, timeout=120):
    """Execute and return the printed output; raise if the server reports an error."""
    result = execute(source, timeout=timeout)
    if result.get("status") != "ok":
        raise RuntimeError(json.dumps(result))
    return result.get("output", "")


TASK = """
import asyncio as _asyncio, json as _json, os as _os, traceback as _traceback
async def _iddmbse_task():
    try:
        result = await _iddmbse_body()
    except Exception:
        result = {"error": _traceback.format_exc()}
    with open(%(tmp)r, "w") as stream:
        _json.dump(result, stream, indent=2)
    _os.replace(%(tmp)r, %(out)r)
_iddmbse_future = _asyncio.ensure_future(_iddmbse_task())
"""


def run_async(source, out, timeout=600):
    """Run a coroutine inside Isaac Sim and wait for its result.

    source defines `async def _iddmbse_body()` returning a JSON-able dict; the
    result is written to out (a local path) when the coroutine finishes, and this
    call returns it, or raises on an error or after timeout seconds.
    """
    out = Path(out).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.unlink(missing_ok=True)
    run(source + TASK % {"tmp": str(out) + ".tmp", "out": str(out)})
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if out.exists():
            result = json.loads(out.read_text())
            if "error" in result:
                raise RuntimeError(result["error"])
            return result
        time.sleep(1.0)
    raise TimeoutError(f"no result at {out} after {timeout} s")


if __name__ == "__main__":
    src = sys.argv[1] if len(sys.argv) > 1 else sys.stdin.read()
    print(json.dumps(execute(src), indent=2))
