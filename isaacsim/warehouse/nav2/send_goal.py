#!/usr/bin/env python3
"""Drive the Carter through the waypoints in waypoints.json with Nav2's NavigateToPose action.

Publishes the initial pose for AMCL, waits for AMCL's estimate and until
bt_navigator is active (its action server rejects goals before that), then
sends the waypoints one after another. While a goal runs it records
/chassis/odom. For every goal it writes one CSV row: the goal, the action status
and Nav2's error code, the simulation start and end times, the odometry path
length, and AMCL's pose at the end. It exits after the last goal.

    python3 nav2/send_goal.py --out results/nav_log.csv [--initial-pose X Y YAW_DEG]

Run it on the same ROS 2 domain and middleware as Nav2 (see start_nav2.sh).
"""

import argparse
import csv
import json
import math
import time
from pathlib import Path

import numpy as np
import rclpy
from action_msgs.msg import GoalStatus
from lifecycle_msgs.msg import State
from lifecycle_msgs.srv import GetState
from geometry_msgs.msg import PoseStamped, PoseWithCovarianceStamped
from nav2_msgs.action import NavigateToPose
from nav_msgs.msg import Odometry
from rclpy.action import ActionClient
from rclpy.node import Node
from rclpy.parameter import Parameter
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy

HERE = Path(__file__).resolve().parent
STATUS = {
    GoalStatus.STATUS_SUCCEEDED: "SUCCEEDED",
    GoalStatus.STATUS_CANCELED: "CANCELED",
    GoalStatus.STATUS_ABORTED: "ABORTED",
}
COLUMNS = [
    "goal", "name", "goal_x", "goal_y", "goal_yaw_deg", "status", "status_code", "error_code", "error_msg",
    "sim_start_s", "sim_end_s", "sim_duration_s", "wall_duration_s", "odom_samples", "odom_path_m",
    "end_amcl_x", "end_amcl_y", "end_amcl_yaw_deg", "end_distance_to_goal_m",
]


def quaternion(yaw):
    return 0.0, 0.0, math.sin(yaw / 2.0), math.cos(yaw / 2.0)


def yaw_of(q):
    return math.atan2(2.0 * (q.w * q.z + q.x * q.y), 1.0 - 2.0 * (q.y * q.y + q.z * q.z))


def path_length(samples):
    if len(samples) < 2:
        return 0.0
    xy = np.asarray(samples)[:, 1:3]
    return float(np.hypot(*np.diff(xy, axis=0).T).sum())


class GoalSender(Node):
    def __init__(self):
        super().__init__("iddmbse_send_goal", parameter_overrides=[Parameter("use_sim_time", value=True)])
        self.samples = []
        self.recording = False
        self.amcl = None
        latched = QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL, reliability=ReliabilityPolicy.RELIABLE)
        self.create_subscription(Odometry, "/chassis/odom", self.on_odom, 50)
        self.create_subscription(PoseWithCovarianceStamped, "/amcl_pose", self.on_amcl, latched)
        self.initial = self.create_publisher(PoseWithCovarianceStamped, "/initialpose", 10)
        self.client = ActionClient(self, NavigateToPose, "navigate_to_pose")

    def on_odom(self, msg):
        if self.recording:
            t = msg.header.stamp.sec + msg.header.stamp.nanosec * 1e-9
            self.samples.append((t, msg.pose.pose.position.x, msg.pose.pose.position.y))

    def on_amcl(self, msg):
        self.amcl = msg

    def sim_now(self):
        return self.get_clock().now().nanoseconds * 1e-9

    def spin_for(self, seconds, until=lambda: False):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline and not until():
            rclpy.spin_once(self, timeout_sec=0.1)
        return until()

    def localise(self, x, y, yaw, timeout):
        msg = PoseWithCovarianceStamped()
        msg.header.frame_id = "map"
        msg.pose.pose.position.x, msg.pose.pose.position.y = x, y
        q = quaternion(yaw)
        msg.pose.pose.orientation.x, msg.pose.pose.orientation.y = q[0], q[1]
        msg.pose.pose.orientation.z, msg.pose.pose.orientation.w = q[2], q[3]
        msg.pose.covariance[0] = msg.pose.covariance[7] = 0.05
        msg.pose.covariance[35] = 0.02
        near = lambda: self.amcl is not None and math.hypot(self.amcl.pose.pose.position.x - x, self.amcl.pose.pose.position.y - y) < 0.5
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            msg.header.stamp = self.get_clock().now().to_msg()
            self.initial.publish(msg)
            if self.spin_for(2.0, near):
                return True
        return False

    def wait_active(self, node_name, timeout):
        client = self.create_client(GetState, node_name + "/get_state")
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if client.wait_for_service(timeout_sec=1.0):
                future = client.call_async(GetState.Request())
                rclpy.spin_until_future_complete(self, future, timeout_sec=5.0)
                if future.done() and future.result().current_state.id == State.PRIMARY_STATE_ACTIVE:
                    return True
            self.spin_for(1.0)
        return False

    def go(self, index, wp, timeout):
        goal = NavigateToPose.Goal()
        goal.pose = PoseStamped()
        goal.pose.header.frame_id = "map"
        goal.pose.header.stamp = self.get_clock().now().to_msg()
        goal.pose.pose.position.x, goal.pose.pose.position.y = float(wp["x"]), float(wp["y"])
        q = quaternion(math.radians(wp["yaw_deg"]))
        goal.pose.pose.orientation.z, goal.pose.pose.orientation.w = q[2], q[3]
        self.samples = []
        self.recording = True
        sim_start, wall_start = self.sim_now(), time.monotonic()
        sent = self.client.send_goal_async(goal)
        rclpy.spin_until_future_complete(self, sent, timeout_sec=30.0)
        handle = sent.result()
        status, error_code, error_msg = "NO_RESPONSE" if handle is None else "REJECTED", "", ""
        if handle is not None and handle.accepted:
            result = handle.get_result_async()
            rclpy.spin_until_future_complete(self, result, timeout_sec=timeout)
            if result.done():
                status_code = result.result().status
                status = STATUS.get(status_code, str(status_code))
                error_code = result.result().result.error_code
                error_msg = result.result().result.error_msg
            else:
                cancel = handle.cancel_goal_async()
                rclpy.spin_until_future_complete(self, cancel, timeout_sec=10.0)
                status, status_code = "TIMEOUT", ""
        else:
            status_code = ""
        self.recording = False
        # the goal's simulation time span, from the odometry stamps recorded while it ran
        sim_start, sim_end = (self.samples[0][0], self.samples[-1][0]) if self.samples else (sim_start, self.sim_now())
        p = self.amcl.pose.pose
        row = {
            "goal": index, "name": wp["name"], "goal_x": wp["x"], "goal_y": wp["y"], "goal_yaw_deg": wp["yaw_deg"],
            "status": status, "status_code": status_code, "error_code": error_code, "error_msg": error_msg,
            "sim_start_s": round(sim_start, 3), "sim_end_s": round(sim_end, 3), "sim_duration_s": round(sim_end - sim_start, 3),
            "wall_duration_s": round(time.monotonic() - wall_start, 1), "odom_samples": len(self.samples),
            "odom_path_m": round(path_length(self.samples), 3),
            "end_amcl_x": round(p.position.x, 3), "end_amcl_y": round(p.position.y, 3),
            "end_amcl_yaw_deg": round(math.degrees(yaw_of(p.orientation)), 1),
            "end_distance_to_goal_m": round(math.hypot(p.position.x - wp["x"], p.position.y - wp["y"]), 3),
        }
        print(json.dumps(row), flush=True)
        return row


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--waypoints", type=Path, default=HERE / "waypoints.json")
    parser.add_argument("--out", type=Path, default=HERE.parent / "results" / "nav_log.csv")
    parser.add_argument("--initial-pose", type=float, nargs=3, metavar=("X", "Y", "YAW_DEG"))
    parser.add_argument("--goal-timeout", type=float, default=900.0, help="wall seconds per goal")
    args = parser.parse_args()
    plan = json.loads(args.waypoints.read_text())
    start = args.initial_pose or (plan["initial_pose"]["x"], plan["initial_pose"]["y"], plan["initial_pose"]["yaw_deg"])

    rclpy.init()
    node = GoalSender()
    if not node.localise(start[0], start[1], math.radians(start[2]), 60.0):
        raise SystemExit("AMCL did not report a pose near the initial pose within 60 s")
    print("localised", round(node.amcl.pose.pose.position.x, 3), round(node.amcl.pose.pose.position.y, 3), flush=True)
    if not node.wait_active("bt_navigator", 300.0) or not node.client.wait_for_server(timeout_sec=60.0):
        raise SystemExit("bt_navigator did not become active within 300 s")
    print("bt_navigator active", flush=True)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS)
        writer.writeheader()
        for index, wp in enumerate(plan["waypoints"], start=1):
            writer.writerow(node.go(index, wp, args.goal_timeout))
            f.flush()
    node.destroy_node()
    rclpy.shutdown()


if __name__ == "__main__":
    main()
