"""A synthetic AGR scenario on the topics `specs/agr_safety.yaml` watches.

Publishes at 10 Hz, for as long as `--duration` says:

    /battery_state      sensor_msgs/BatteryState   percentage = 0.9 - 0.015 t, so it crosses
                                                   0.6 at t = 20 s and the soc_safety monitor
                                                   must report a violation there
    /goal_reached       std_msgs/Bool              False until t = 28 s, True after, so the
                                                   goal_liveness robustness flips sign
    /obstacle_distance  std_msgs/Float64           1.2 + 0.4 sin(0.5 t), never below 0.8, so
                                                   the obstacle_safety monitor stays satisfied

Run it with ROS 2 sourced, in a second shell alongside `stl_observer_node.py`.
"""

import argparse
import math

import rclpy
from rclpy.node import Node
from sensor_msgs.msg import BatteryState
from std_msgs.msg import Bool, Float64

RATE = 10.0


class Scenario(Node):
    def __init__(self, duration, soc0, soc_slope, goal_at):
        super().__init__("veritas_test_publisher")
        self.duration = duration
        self.soc0 = soc0
        self.soc_slope = soc_slope
        self.goal_at = goal_at
        self.t = 0.0
        self.battery = self.create_publisher(BatteryState, "/battery_state", 10)
        self.goal = self.create_publisher(Bool, "/goal_reached", 10)
        self.obstacle = self.create_publisher(Float64, "/obstacle_distance", 10)
        self.create_timer(1.0 / RATE, self.tick)
        self.get_logger().info("publishing the synthetic scenario, soc crosses 0.6 at t="
                               + str(round((self.soc0 - 0.6) / self.soc_slope, 2)) + "s")

    def tick(self):
        if self.duration and self.t > self.duration:
            raise SystemExit(0)
        b = BatteryState()
        b.header.stamp = self.get_clock().now().to_msg()
        b.percentage = float(self.soc0 - self.soc_slope * self.t)
        b.voltage = float(24.0 * b.percentage)
        self.battery.publish(b)
        self.goal.publish(Bool(data=bool(self.t >= self.goal_at)))
        self.obstacle.publish(Float64(data=float(1.2 + 0.4 * math.sin(0.5 * self.t))))
        self.t += 1.0 / RATE


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--duration", type=float, default=32.0)
    p.add_argument("--soc0", type=float, default=0.9)
    p.add_argument("--soc-slope", type=float, default=0.015)
    p.add_argument("--goal-at", type=float, default=28.0)
    a = p.parse_args()

    rclpy.init()
    node = Scenario(a.duration, a.soc0, a.soc_slope, a.goal_at)
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, SystemExit):
        pass
    finally:
        node.destroy_node()
        rclpy.try_shutdown()


main()
