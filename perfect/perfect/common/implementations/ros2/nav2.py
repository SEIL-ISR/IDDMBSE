FILE = "nav2_params.yaml"

def controller(data: dict) -> dict:
    if data["name"] == "DWB":
        parameters = [
            {'name': 'acc_lim_theta', 'default': 3.2},
            {'name': 'acc_lim_x', 'default': 2.5},
            {'name': 'acc_lim_y', 'default': 0.0},
            {'name': 'decel_lim_theta', 'default': -3.2},
            {'name': 'decel_lim_x', 'default': -2.5},
            {'name': 'decel_lim_y', 'default': 0.0},
            {'name': 'max_speed_xy', 'default': 1.0},
            {'name': 'max_vel_theta', 'default': 1.2},
            {'name': 'max_vel_x', 'default': 1.8},
            {'name': 'max_vel_y', 'default': 0.0},
            {'name': 'min_speed_theta', 'default': 0.0},
            {'name': 'min_speed_xy', 'default': 0.0},
            {'name': 'min_vel_x', 'default': 0.0},
            {'name': 'min_vel_y', 'default': 0.0},
        ]
        followpath = {
            "plugin": "dwb_core::DWBLocalPlanner",
            "critics": [
                "BaseObstacle",
                "GoalAlign",
                "GoalDist",
                "Oscillation",
                "PathAlign",
                "PathDist",
                "RotateToGoal",
            ],
            'acc_lim_theta': '$acc_lim_theta',
            'acc_lim_x': '$acc_lim_x',
            'acc_lim_y': '$acc_lim_y',
            "angular_granularity": 0.025,
            "BaseObstacle.scale": 0.02,
            'decel_lim_theta': '$decel_lim_theta',
            'decel_lim_x': '$decel_lim_x',
            'decel_lim_y': '$decel_lim_y',
            "GoalAlign.forward_point_distance": 0.1,
            "GoalAlign.scale": 24.0,
            "GoalDist.scale": 24.0,
            "linear_granularity": 0.05,
            'max_speed_xy': '$max_speed_xy',
            'max_vel_theta': '$max_vel_theta',
            'max_vel_x': '$max_vel_x',
            'max_vel_y': '$max_vel_y',
            'min_speed_theta': '$min_speed_theta',
            'min_speed_xy': '$min_speed_xy',
            'min_vel_x': '$min_vel_x',
            'min_vel_y': '$min_vel_y',
            "PathAlign.forward_point_distance": 0.1,
            "PathAlign.scale": 32.0,
            "PathDist.scale": 32.0,
            "RotateToGoal.lookahead_time": -1.0,
            "RotateToGoal.scale": 32.0,
            "RotateToGoal.slowing_factor": 5.0,
            "sim_time": 1.7,
            "stateful": True,
            "transform_tolerance": 0.2,
            "trans_stopped_velocity": 0.25,
            "vtheta_samples": 20,
            "vx_samples": 20,
            "vy_samples": 5,
            "xy_goal_tolerance": 0.25,
        }
    elif data["name"] == "MPPI":
        parameters = [
            {'name': 'vx_max', 'default': 1.8},
            {'name': 'vx_min', 'default': -0.35},
            {'name': 'vx_std', 'default': 0.2},
            {'name': 'vy_max', 'default': 0.5},
            {'name': 'vy_std', 'default': 0.2},
            {'name': 'wz_max', 'default': 1.2},
            {'name': 'wz_std', 'default': 0.4}
        ]
        followpath = {
            "plugin": "nav2_mppi_controller::MPPIController",
            "critics": [
                "ConstraintCritic",
                "CostCritic",
                "GoalCritic",
                "GoalAngleCritic",
                "PathAlignCritic",
                "PathFollowCritic",
                "PathAngleCritic",
                "PreferForwardCritic"
            ],
            "batch_size": 2000,
            "gamma": 0.015,
            "iteration_count": 1,
            "model_dt": 0.05,
            "motion_model": "DiffDrive",
            "prune_distance": 1.7,
            "temperature": 0.3,
            "time_steps": 56,
            "transform_tolerance": 0.1,
            'vx_max': '$vx_max',
            'vx_min': '$vx_min',
            'vx_std': '$vx_std',
            'vy_max': '$vy_max',
            'vy_std': '$vy_std',
            'wz_max': '$wz_max',
            'wz_std': '$wz_std',
        }
    else:
        raise NotImplementedError
    return {
        "parameters": parameters,
        "files": [
            {
                "file": FILE,
                "updates": [
                    {
                        "keys": "controller_server.ros__parameters.FollowPath",
                        "value": followpath,
                    }
                ]
            }
        ]
    }

def planner(data: dict) -> dict:
    # Would it be better to provide A* as a specific kind of NavFn, instead of (at the user level) a wholly different planner?
    known_planners = {
        "A*": "nav2_navfn_planner/NavfnPlanner",
        "NavFn": "nav2_navfn_planner/NavfnPlanner",
    }
    try:
        use_astar = data["name"] == "A*"
        planner = known_planners[data["name"]]
    except KeyError:
        raise NotImplementedError
    return {
        "parameters": [
            {"name": "tolerance", "default": 0.5},
        ],
        "files": [
            {
                "file": FILE,
                "updates": [
                    {
                        "keys": "planner_server.ros__parameters.GridBased",
                        "value": {
                            "plugin": planner,
                            "tolerance": "$tolerance",
                            "use_astar": use_astar,
                            "allow_unknown": True,
                        },
                    }
                ]
            }
        ]
    }
