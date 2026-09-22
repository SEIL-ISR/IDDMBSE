"""VERITAS runtime observer: a generic-subscriber ROS 2 node that monitors STL obligations.

Reads a YAML spec (see `monitors.py` for the format), subscribes to whatever topics the spec
names -- the message type is resolved at run time from its string with
`rosidl_runtime_py.utilities.get_message`, so a new signal on a new topic of a new type needs
an edit to the YAML and nothing else, no rebuild -- samples every signal at a fixed rate,
feeds each RTAMT monitor online, and publishes

    /veritas/<monitor>/robustness   std_msgs/Float64
    /veritas/<monitor>/violation    std_msgs/Bool

A monitor starts publishing once every signal it needs has been received at least once; the
sampler holds the last value between messages (zero-order hold).  Entering and leaving
violation is logged at warning level.

Run it with ROS 2 sourced, outside the veritas uv venv:

    python3 stl_observer_node.py --spec specs/agr_safety.yaml --duration 40
"""

import argparse
import os
import sys

import rclpy
from rclpy.node import Node
from rosidl_runtime_py.utilities import get_message
from std_msgs.msg import Bool, Float64

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from monitors import load_spec, read_field  # noqa: E402


class StlObserver(Node):
    def __init__(self, spec_path, duration):
        super().__init__("veritas_stl_observer")
        self.rate, self.monitors, self.sources = load_spec(spec_path)
        self.values = {}
        self.duration = duration
        self.elapsed = 0.0

        self.subs = []
        for name, src in self.sources.items():
            cls = get_message(src["type"])
            self.subs.append(self.create_subscription(
                cls, src["topic"], self.make_cb(name, src["field"]), 10))
            self.get_logger().info(
                "signal " + name + " <- " + src["topic"] + " (" + src["type"] + "." + src["field"] + ")")

        self.pubs = {}
        for m in self.monitors:
            self.pubs[m.name] = (
                self.create_publisher(Float64, "/veritas/" + m.name + "/robustness", 10),
                self.create_publisher(Bool, "/veritas/" + m.name + "/violation", 10),
            )
            self.get_logger().info(
                "monitor " + m.name + " [" + m.requirement + "]: " + m.formula)

        self.create_timer(1.0 / self.rate, self.sample)

    def make_cb(self, name, field):
        def cb(msg):
            self.values[name] = read_field(msg, field)
        return cb

    def sample(self):
        self.elapsed += 1.0 / self.rate
        if self.duration and self.elapsed > self.duration:
            raise SystemExit(0)
        for m in self.monitors:
            if not all(s in self.values for s in m.signals):
                continue
            was = m.violated
            rho, violated = m.step(self.values)
            rob, vio = self.pubs[m.name]
            rob.publish(Float64(data=float(rho)))
            vio.publish(Bool(data=bool(violated)))
            if violated and not was:
                self.get_logger().warn(
                    "VIOLATION " + m.name + " [" + m.requirement + "] at t=" + str(round(m.time, 2))
                    + "s robustness " + str(round(rho, 4)) + " : " + m.formula)
            elif was and not violated:
                self.get_logger().warn(
                    "recovered " + m.name + " at t=" + str(round(m.time, 2))
                    + "s robustness " + str(round(rho, 4)))


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--spec", default=os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                                  "specs", "agr_safety.yaml"))
    p.add_argument("--duration", type=float, default=0.0, help="seconds before the node exits; 0 = forever")
    a = p.parse_args()

    rclpy.init()
    node = StlObserver(a.spec, a.duration)
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, SystemExit):
        pass
    finally:
        node.destroy_node()
        rclpy.try_shutdown()


main()
