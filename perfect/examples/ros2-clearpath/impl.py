import math

from perfect.common.implementations.ros2 import nav2

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
STEREOLABS = "Stereolabs"
VELODYNE = "Velodyne"

def convert(data: dict) -> dict:
    brand, type_ = data["brand"], data["type"]
    if type_ == GLOBAL_PLANNER:
        impl = nav2.planner(data)
    elif type_ == LOCAL_PLANNER:
        impl = nav2.controller(data)
    elif (brand, type_) == (VELODYNE, LIDAR3D):
        impl = _velodyne_lidar3d(data)
    elif (brand, type_) == (HOKUYO, LIDAR2D):
        impl = _hokuyo_lidar2d(data)
    elif (brand, type_) == (SICK, LIDAR2D):
        impl = _sick_lidar2d(data)
    elif (brand, type_) == (INTEL, CAMERA):
        impl = _intel_camera(data)
    elif (brand, type_) == (FLIR, CAMERA):
        impl = _flir_camera(data)
    elif (brand, type_) == (STEREOLABS, CAMERA):
        impl = _stereolabs_camera(data)
    else:
        raise NotImplementedError
    return {
        "name": f"{data['brand']} {data['name']}" if data['brand'] else data['name'],
        "type": data["type"],
        "implementation": impl,
    }


def _velodyne_lidar3d(data: dict) -> dict:
    if "VLP-16 Puck" == data["name"]:
        calibration = "/opt/ros/humble/share/velodyne_pointcloud/params/VLP16db.yaml"
        model = "VLP16"
    elif "VLP-32C Ultra Puck" == data["name"]:
        calibration = "/opt/ros/humble/share/velodyne_pointcloud/params/VeloView-VLP-32C.yaml"
        model = "32C"
    elif "VLS-128 Alpha Prime" == data["name"]:
        calibration = "/opt/ros/humble/share/velodyne_pointcloud/params/VLS128.yaml"
        model = "VLS128"
    elif "HDL-32E" == data["name"]:
        calibration = "/opt/ros/humble/share/velodyne_pointcloud/params/32db.yaml"
        model = "32E"
    elif "HDL-64E" == data["name"]:
        calibration = "/opt/ros/humble/share/velodyne_pointcloud/params/64e_utexas.yaml"
        model = "64E"
    elif "HDL-64ES2" == data["name"]:
        calibration = "/opt/ros/humble/share/velodyne_pointcloud/params/64e_s2.1-sztaki.yaml"
        model = "64E_S2"
    elif "HDL-64ES3" == data["name"]:
        calibration = "/opt/ros/humble/share/velodyne_pointcloud/params/64e_s3-xiesc.yaml"
        model = "64E_S3"
    else:
        raise NotImplementedError
    return {
        "parameters": [
            {"name": "parent_frame", "default": "sensor_arch_mount"}
        ],
        "files": [
            {
                "file": "robot.yaml",
                "updates": [
                    {
                        "keys": "sensors.lidar3d",
                        "value": [
                            {
                                "model": "velodyne_lidar",
                                "urdf_enabled": True,
                                "launch_enabled": True,
                                "parent": "$parent_frame",
                                "xyz": [ 0.0, 0.0, 0.0 ],
                                "rpy": [ 0.0, 0.0, 0.0 ],
                                "ros_parameters": {
                                    "velodyne_driver_node": {
                                        "frame_id": "lidar3d_$i_laser",
                                        "model": model
                                    },
                                    "velodyne_transform_node": {
                                        "model": model,
                                        "calibration": calibration,
                                        "fixed_frame": "lidar3d_$i_laser",
                                        "target_frame": "lidar3d_$i_laser"
                                    }
                                }
                            }
                        ]
                    }
                ]
            }
        ]
    }


def _hokuyo_lidar2d(data: dict) -> dict:
    if "UST" not in data["name"]:
        raise NotImplementedError
    return {
        "parameters": [
            {"name": "x", "default": 0.0},
            {"name": "y", "default": 0.0},
            {"name": "parent_frame", "default": "bracket_$i_mount"}
        ],
        "files": [
            {
                "file": "robot.yaml",
                "updates": [
                    {
                        "keys": "sensors.lidar2d",
                        "value": [
                            {
                                "model": "hokuyo_ust",
                                "urdf_enabled": True,
                                "launch_enabled": True,
                                "parent": "$parent_frame",
                                "xyz": [ "$x", "$y", 0.0 ],
                                "rpy": [ 0.0, 0.0, 0.0 ],
                                "ros_parameters": {
                                    "urg_node": {
                                        "laser_frame_id": "lidar2d_$i_laser",
                                        "angle_min": math.radians(data["field_of_view_vertical_down"]),
                                        "angle_max": math.radians(data["field_of_view_vertical_up"])
                                    }
                                }
                            }
                        ]
                    }
                ]
            }
        ]
    }


def _sick_lidar2d(data: dict) -> dict:
    if not data["name"].startswith("LMS1"):
        raise NotImplementedError
    return {
        "parameters": [
            {"name": "parent_frame", "default": "bracket_$i_mount"}
        ],
        "files": [
            {
                "file": "robot.yaml",
                "updates": [
                    {
                        "keys": "sensors.lidar2d",
                        "value": [
                            {
                                "model": "sick_lms1xx",
                                "urdf_enabled": True,
                                "launch_enabled": True,
                                "parent": "$parent_frame",
                                "xyz": [ 0.0, 0.0, 0.0 ],
                                "rpy": [ 0.0, 0.0, 0.0 ],
                                "ros_parameters": {
                                    "lms1xx": {
                                        "laser_frame_id": "lidar2d_0_laser"
                                    }
                                }
                            }
                        ]
                    }
                ]
            }
        ]
    }


def _intel_camera(data: dict) -> dict:
    if "D435" in data["name"]:
        device_type = "d435"
        # TODO: rgb_camera.profile and/or depth_module.profile??
    else:
        raise NotImplementedError
    return {
        "parameters": [
            {"name": "parent_frame", "default": "fath_pivot_$i_mount"}
        ],
        "files": [
            {
                "file": "robot.yaml",
                "updates": [
                    {
                        "keys": "sensors.camera",
                        "value": [
                            {
                                "model": "intel_realsense",
                                "urdf_enabled": True,
                                "launch_enabled": True,
                                "parent": "$parent_frame",
                                "xyz": [ 0.0, 0.0, 0.0 ],
                                "rpy": [ 0.0, 0.0, 0.0 ],
                                "ros_parameters": {
                                    "intel_realsense": {
                                        "camera_name": "camera_$i",
                                        "device_type": device_type,
                                        "serial_no": "0",
                                        "enable_color": True,
                                        "rgb_camera.profile": [ 640, 480, 30 ],  # TODO get from datasheet
                                        "enable_depth": True,
                                        "depth_module.profile": [ 640, 480, 30 ],  # TODO get from datasheet
                                        "pointcloud.enable": True
                                    }
                                }
                            }
                        ]
                    }
                ]
            }
        ]
    }


def _flir_camera(data: dict) -> dict:
    if "Blackfly S" != data["name"]:
        raise NotImplementedError
    return {
        "parameters": [
            {"name": "frame_rate", "default": 40},  # TODO get default value from datasheet
            {"name": "parent_frame", "default": "fath_pivot_$i_mount"}
        ],
        "files": [
            {
                "file": "robot.yaml",
                "updates": [
                    {
                        "keys": "sensors.camera",
                        "value": [
                            {
                                "model": "flir_blackfly",
                                "urdf_enabled": True,
                                "launch_enabled": True,
                                "parent": "$parent_frame",
                                "xyz": [ 0.0, 0.0, 0.0 ],
                                "rpy": [ 0.0, 0.0, 0.0 ],
                                "ros_parameters": {
                                    "flir_blackfly": {
                                        "serial_number": "",
                                        "gain_auto": "Continuous",
                                        "pixel_format": "BayerRG8",
                                        "frame_rate_enable": True,
                                        "frame_rate_auto": "Off",
                                        "frame_rate": "$frame_rate"
                                    }
                                }
                            }
                        ]
                    }
                ]
            }
        ]
    }


def _stereolabs_camera(data: dict) -> dict:
    if "ZED" not in data["name"]:
        raise NotImplementedError
    return {
        "parameters": [
            {"name": "parent_frame", "default": "fath_pivot_$i_mount"}
        ],
        "files": [
            {
                "file": "robot.yaml",
                "updates": [
                    {
                        "keys": "sensors.camera",
                        "value": [
                            {
                                "model": "stereolabs_zed",
                                "urdf_enabled": True,
                                "launch_enabled": True,
                                "parent": "$parent_frame",
                                "xyz": [ 0.0, 0.0, 0.0 ],
                                "rpy": [ 0.0, 0.0, 0.0 ],
                                "ros_parameters": {
                                    "stereolabs_zed": {
                                        "general.grab_frame_rate": 30,  # TODO get from data?
                                        "general.serial_number": 0,
                                        "general.camera_model": "zed2",
                                        "general.grab_resolution": "AUTO"
                                    }
                                }
                            }
                        ]
                    }
                ]
            }
        ]
    }
