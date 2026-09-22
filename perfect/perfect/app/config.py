import os

from perfect import common


class Config:
    # System configuration
    SECRET_KEY = os.environ.get("SECRET_KEY") or "openphrase123"

    # Project configuration
    PERFECT_PROJECT_ROOT = os.environ["PERFECT_PROJECT_ROOT"].rstrip("/")
    PERFECT_PROJECT_NAME = os.environ.get("PERFECT_PROJECT_NAME") or os.path.basename(
        PERFECT_PROJECT_ROOT
    )
    REDIS_URL = os.environ.get("REDIS_URL") or "redis://"
    SQLALCHEMY_DATABASE_URI = (
        os.environ.get("PERFECT_PROJECT_DATABASE_URI")
        or f"sqlite:///{PERFECT_PROJECT_ROOT}/{PERFECT_PROJECT_NAME}.db"
    )
    RUNNER_PORT = common.RUNNER_PORT
    RUNNER_URIS = (
        os.environ.get("RUNNER_URIS") or f"ws://localhost:{common.RUNNER_PORT}"
    ).split(",")

    RUN_LOCALLY = False

    # Worker/task configuration
    RUNNER_CONNECT_TIMEOUT_SEC = 3
    CHECK_CANCELLED_PERIOD_SEC = 1
    CYCLE_RUNNERS_PERIOD_SEC = 5

    # Experiment configuration
    CALLBACKS_LOOP_CHECK_READY_PERIOD_SEC = 1
    CALLBACKS_LOOP_CHECK_COMPLETE_PERIOD_SEC = 0.5
    RUN_CHECK_READY_PERIOD_SEC = 0.5

    # ROS experiment configuration
    PAUSE_BEFORE_READY_SEC = 3
    PAUSE_AFTER_INITS_SEC = 3
    RCLPY_SPIN_TIMEOUT_SEC = 0.01
    RCLPY_SPIN_PERIOD_SEC = 0.001
    TIMEOUT_SEC = 300

    # Records, including rosbags, pip list, design/environment implementations, etc.
    RECORDS_ENABLED = False
    RECORDS_ROOT = os.path.join(os.environ["PERFECT_PROJECT_ROOT"], "records")
