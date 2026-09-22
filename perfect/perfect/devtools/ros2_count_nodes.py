import time

import rclpy
from ros2node.api import get_node_names

NODE = "node_listing_node"

rclpy.init()
node = rclpy.create_node(NODE)

prev_n = None
t = time.time()
while True:
    n = len(get_node_names(node=node, include_hidden_nodes=False))
    if n != prev_n:
        elapsed = time.time() - t
        t = time.time()
        print(f"{elapsed:5.1f} There are {n} nodes (including {NODE})")
        prev_n = n
    time.sleep(.1)
