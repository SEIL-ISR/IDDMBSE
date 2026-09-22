from perfect.common.implementations.ros2 import nav2


NAVIGATION = "navigation"
GLOBAL_PLANNER = "global_planner"
LOCAL_PLANNER = "local_planner"

SENSOR_TYPES = [
    "camera",
    "depth_camera",
    "lidar2d",
    "lidar3d"
]


def convert(data: dict) -> dict:
    _, type_ = data["brand"], data["type"]
    if type_ == GLOBAL_PLANNER:
        impl = nav2.planner(data)
    elif type_ == LOCAL_PLANNER:
        impl = nav2.controller(data)
    elif type_ in SENSOR_TYPES:
        impl = _sensor_component(data)
    else:
        raise NotImplementedError
    return {
        "name": f"{data['brand']} {data['name']}" if data['brand'] else data['name'],
        "type": data["type"],
        "implementation": impl,
    }


def _sensor_component(data: dict) -> dict:
    subpath = f"{data['type']}_{data['brand']}_{data['name']}".replace(" ", "")
    return {
        "parameters": [],
        "files": [
            {
                "file": "robot.usd",
                "updates": [
                    {
                        "prim": f"/husky_ros2_sensors/{subpath}/render_product",
                        "attribute": "input:enabled",
                        "value": True
                    }
                ]
            }
        ]
    }
