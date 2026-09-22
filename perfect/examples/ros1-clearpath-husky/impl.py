import os


NAVIGATION = "navigation"
GLOBAL_PLANNER = "global_planner"
LOCAL_PLANNER = "local_planner"

CAMERA = "camera"
DEPTH_CAMERA = "depth_camera"
LIDAR2D = "lidar2d"
LIDAR3D = "lidar3d"

FLIR = "FLIR"
HOKUYO = "Hokuyo"
INTEL = "Intel"
SICK = "SICK"
VELODYNE = "Velodyne"


# Prepare sensor data for Clearpath Husky
def convert(data: dict) -> dict:
    brand, type_ = data["brand"], data["type"]
    if (brand, type_) == (VELODYNE, LIDAR3D):
        impl = _velodyne_lidar3d(data)
    elif (brand, type_) == (SICK, LIDAR2D):
        impl = _sick_lidar2d(data)
    elif (brand, type_) == (HOKUYO, LIDAR2D):
        impl = _hokuyo_lidar2d(data)
    elif (brand, type_) == (INTEL, CAMERA):
        impl = _intel_camera(data)
    elif (brand, type_) == (FLIR, CAMERA):
        impl = _flir_camera(data)
    elif (type_) == (NAVIGATION):
        impl = _nav(data)
    elif (type_) in [GLOBAL_PLANNER, LOCAL_PLANNER]:
        impl = _planner(data)
    else:
        raise NotImplementedError
    return {
        "name": f"{data['brand']} {data['name']}" if data['brand'] else data['name'],
        "type": data["type"],
        "implementation": impl,
    }


def _velodyne_lidar3d(data: dict) -> dict:
    if data["name"] == "VLP-16 Puck":
        return {
            "parameters": [
            ],
            "envvars": [
                {"envvar": "HUSKY_LASER_3D_ENABLED", "value": "true"},
                {"envvar": "HUSKY_LASER_3D_XYZ", "value": "0.0 0.0 0.0"},
                {"envvar": "HUSKY_LASER_3D_RPY", "value": "0.0 0.0 0.0"},
                {"envvar": "HUSKY_LASER_3D_TOPIC", "value": "velodyne_points"},
            ],
            "launchargs": [
                {"arg": "rtabmap_lidar3d", "value": "true"}
            ]
        }
    elif data["name"] == "HDL-32E":
        return {
            "parameters": [
            ],
            "envvars": [
                {"envvar": "HUSKY_LASER_3D_ENABLED", "value": "false"},
                {"envvar": "HUSKY_HDL32E_ENABLED", "value": "true"},
                {"envvar": "HUSKY_LASER_3D_XYZ", "value": "0.0 0.0 0.0"},
                {"envvar": "HUSKY_LASER_3D_RPY", "value": "0.0 0.0 0.0"},
                {"envvar": "HUSKY_LASER_3D_TOPIC", "value": "velodyne_points"},
                {"envvar": "HUSKY_URDF_EXTRAS", "value": f"{os.environ['PERFECT_PROJECT_ROOT']}/urdf/hdl32e.urdf.xacro"},
            ],
            "launchargs": [
                {"arg": "rtabmap_lidar3d", "value": "true"}
            ]
        }
    else:
        raise NotImplementedError


def _sick_lidar2d(data: dict) -> dict:
    if not data["name"].startswith("LMS1"):
        raise NotImplementedError
    return {
        "parameters": [
            {"name": "$enabled_envvar", "default": "HUSKY_LMS1XX_ENABLED"},
            {"name": "$xyz_envvar", "default": "HUSKY_LMS1XX_XYZ"},
            {"name": "$xyz", "default": "0.2206 0.0 0.00635"},
            {"name": "$rpy_envvar", "default": "HUSKY_LMS1XX_RPY"},
            {"name": "$rpy", "default": "0.0 0.0 0.0"}
        ],
        "envvars": [
            {"envvar": "$enabled_envvar", "value": "true"},
            {"envvar": "$xyz_envvar", "value": "$xyz"},
            {"envvar": "$rpy_envvar", "value": "$rpy"},
        ],
        "launchargs": [
            {"arg": "rtabmap_lidar2d", "value": "true"}
        ]
    }

def _hokuyo_lidar2d(data: dict) -> dict:
    if "UST" not in data["name"]:
        raise NotImplementedError
    return {
        "parameters": [
        ],
        "envvars": [
            {"envvar": "HUSKY_UST10_ENABLED", "value": "true"},
            {"envvar": "HUSKY_UST10_XYZ", "value": "0.2206 0.0 0.00635"},
        ],
        "launchargs": [
            {"arg": "rtabmap_lidar2d", "value": "true"}
        ]
    }

def _intel_camera(data: dict) -> dict:
    if data["name"].endswith("D455"):
        model = "d455"
    elif data["name"].endswith("D435"):
        model = "d435"
    elif data["name"].endswith("D415"):
        model = "d415"
    else:
        raise NotImplementedError
    return {
        "parameters": [
        ],
        "envvars": [
            {"envvar": "HUSKY_REALSENSE_ENABLED", "value": "true"},
            {"envvar": "HUSKY_REALSENSE_MODEL", "value": model},
            {"envvar": "HUSKY_REALSENSE_XYZ", "value": "0.35 0.0 0.0"},
        ],
        "launchargs": [
            {"arg": "rtabmap_camera", "value": "true"},
            {"arg": "rtabmap_depth_from_lidar", "value": "false"},
            {"arg": "rtabmap_rgb_topic", "value": "/realsense/color/image_raw"},
            {"arg": "rtabmap_camera_info_topic", "value": "/realsense/color/camera_info"},
            {"arg": "rtabmap_depth_topic", "value": "/realsense/depth/image_rect_raw"},
        ]
    }

def _flir_camera(data: dict) -> dict:
    if data["name"] != "Blackfly S":
        raise NotImplementedError
    return {
        "parameters": [
        ],
        "envvars": [
            {"envvar": "HUSKY_BLACKFLY", "value": "1"},
            {"envvar": "HUSKY_BLACKFLY_XYZ", "value": "0.35 0.0 0.0"},
        ],
        "launchargs": [
            {"arg": "rtabmap_camera", "value": "true"},
            {"arg": "rtabmap_depth_from_lidar", "value": "true"},  # Note that this requires the use of a 3D LiDAR (e.g., Puck)
            {"arg": "rtabmap_rgb_topic", "value": "/camera/image_raw"},
            {"arg": "rtabmap_camera_info_topic", "value": "/camera/camera_info"},
        ]
    }

def _nav(data: dict) -> dict:
    if data["name"] != "RTAB-Map":
        raise NotImplementedError
    return {
        "parameters": [
        ],
        "launchargs": [
            {"arg": "rtabmap_icp_odometry",        "value": "false"},
            {"arg": "rtabmap_lidar3d_ray_tracing", "value": "true"},
            {"arg": "rtabmap_slam2d",              "value": "true"}
        ]
    }

def _planner(data: dict) -> dict:
    known_planners = {
        "Dynamic Window Approach": ("base_local_planner", "dwa_local_planner/DWAPlannerROS"),
        "Trajectory Rollout": ("base_local_planner", "base_local_planner/TrajectoryPlannerROS"),
        "Teb": ("base_local_planner", "teb_local_planner/TebLocalPlannerROS"),
        "NavFn": ("base_global_planner", "navfn/NavfnROS"),
    }
    try:
        planner_type, planner = known_planners[data["name"]]
    except KeyError:
        raise NotImplementedError
    return {
        "parameters": [
        ],
        "launchargs": [
            {"arg": planner_type, "value": planner}
        ]
    }