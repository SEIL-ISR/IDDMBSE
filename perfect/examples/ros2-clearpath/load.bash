# All designs, environments, and experiments we create here will have the same tag
TAG=demo
# All Flask calls start with this
PERFECT_CMD="python -m flask --app perfect.app"

# Reset the database
rm -rf migrations/ *.db*
$PERFECT_CMD db init
$PERFECT_CMD db migrate -m "Initial migration."
$PERFECT_CMD db upgrade

# Load the sensor components into the database
$PERFECT_CMD components load_components

# Create some hand-picked designs
$PERFECT_CMD designs create lidar2d=UST camera=Blackfly planner=NavFn controller=DWB --template clearpath_husky_vision --name "Husky (UST, Blackfly S)" --tag $TAG
$PERFECT_CMD designs create lidar2d=LMS111 camera=Blackfly planner=NavFn controller=DWB --template clearpath_husky_vision --name "Husky (LMS111, Blackfly S)" --tag $TAG
$PERFECT_CMD designs create lidar2d=LMS151 "camera=Blackfly S" planner=NavFn controller=DWB --template clearpath_husky_vision --name "Husky (LMS151, Blackfly S)" --tag $TAG
$PERFECT_CMD designs create lidar3d=Puck lidar2d=UST "camera=Blackfly S" planner=NavFn controller=DWB --template clearpath_husky_vision --name "Husky (Puck, UST, Blackfly S)" --tag $TAG --parameters '{"lidar2d": {"0": {"$x": 0.5}}}'

$PERFECT_CMD environments create_templates_from_file navigate_from_initial_pose_to_goal_pose.json

# Create environments with various start/goal positions
$PERFECT_CMD environments create_from_template 1 x_start:=0.0 y_start:=0.0 x_goal:=3.0 y_goal:=0.0 --name "Move forward 3m" --tag $TAG
$PERFECT_CMD environments create_from_template 1 x_start:=0.0 y_start:=0.0 x_goal:=10.0 y_goal:=0.0 --name "Move forward 10m" --tag $TAG
$PERFECT_CMD environments create_from_template 1 x_start:=0.0 y_start:=0.0 x_goal:=1.0 y_goal:=-4.0 --name "Move around" --tag $TAG

# Create experiments for all combinations of designs and environments that have our tag
# FIXME see comment in perfect.app.routes.experiments about assuming patterns are tags
$PERFECT_CMD experiments create $TAG $TAG --tag $TAG

# Run (enqueue) experiments that have our tag
# FIXME similar issue about patterns just being tags for now
#$PERFECT_CMD experiments run $TAG
