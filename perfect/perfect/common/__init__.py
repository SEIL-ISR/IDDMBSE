import os
import pathlib

PATH = pathlib.Path(__file__).parent

# The port the PERFECT runner's websocket server listens on. Read here so that
# the runner and the server's RUNNER_URIS default cannot drift apart.
RUNNER_PORT = int(os.environ.get("RUNNER_PORT") or 8003)
