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
$PERFECT_CMD designs create lidar2d=UST    camera=D415 navigation=RTAB global_planner=NavFn local_planner=Dynamic --template clearpath_husky --name "Husky (UST, D415)" --tag $TAG
$PERFECT_CMD designs create lidar2d=LMS111 camera=D415 navigation=RTAB global_planner=NavFn local_planner=Dynamic --template clearpath_husky --name "Husky (LMS1XX, D415)" --tag $TAG
$PERFECT_CMD designs create lidar3d=Puck   camera=D415 navigation=RTAB global_planner=NavFn local_planner=Dynamic --template clearpath_husky --name "Husky (Puck, D415)" --tag $TAG

$PERFECT_CMD designs create lidar3d="HDL-32E"   camera=D415 navigation=RTAB global_planner=NavFn local_planner=Dynamic --template clearpath_husky --name "Husky (HDL-32E, D415)" --tag $TAG

$PERFECT_CMD designs create lidar2d=UST    camera=D435 navigation=RTAB global_planner=NavFn local_planner=Dynamic --template clearpath_husky --name "Husky (UST, D435)" --tag $TAG
$PERFECT_CMD designs create lidar2d=LMS111 camera=D435 navigation=RTAB global_planner=NavFn local_planner=Dynamic --template clearpath_husky --name "Husky (LMS1XX, D435)" --tag $TAG
$PERFECT_CMD designs create lidar3d=Puck   camera=D435 navigation=RTAB global_planner=NavFn local_planner=Dynamic --template clearpath_husky --name "Husky (Puck, D435)" --tag $TAG

$PERFECT_CMD designs create lidar2d=UST    camera=D455 navigation=RTAB global_planner=NavFn local_planner=Dynamic --template clearpath_husky --name "Husky (UST, D455)" --tag $TAG
$PERFECT_CMD designs create lidar2d=LMS111 camera=D455 navigation=RTAB global_planner=NavFn local_planner=Dynamic --template clearpath_husky --name "Husky (LMS1XX, D455)" --tag $TAG
$PERFECT_CMD designs create lidar3d=Puck   camera=D455 navigation=RTAB global_planner=NavFn local_planner=Dynamic --template clearpath_husky --name "Husky (Puck, D455)" --tag $TAG

$PERFECT_CMD designs create lidar2d=UST    camera=D415 navigation=RTAB global_planner=NavFn local_planner=Teb --template clearpath_husky --name "Husky (UST, D415, Teb)" --tag $TAG
$PERFECT_CMD designs create lidar2d=LMS111 camera=D415 navigation=RTAB global_planner=NavFn local_planner=Teb --template clearpath_husky --name "Husky (LMS1XX, D415, Teb)" --tag $TAG
$PERFECT_CMD designs create lidar3d=Puck   camera=D415 navigation=RTAB global_planner=NavFn local_planner=Teb --template clearpath_husky --name "Husky (Puck, D415, Teb)" --tag $TAG

$PERFECT_CMD designs create lidar2d=UST    camera=D435 navigation=RTAB global_planner=NavFn local_planner=Teb --template clearpath_husky --name "Husky (UST, D435, Teb)" --tag $TAG
$PERFECT_CMD designs create lidar2d=LMS111 camera=D435 navigation=RTAB global_planner=NavFn local_planner=Teb --template clearpath_husky --name "Husky (LMS1XX, D435, Teb)" --tag $TAG
$PERFECT_CMD designs create lidar3d=Puck   camera=D435 navigation=RTAB global_planner=NavFn local_planner=Teb --template clearpath_husky --name "Husky (Puck, D435, Teb)" --tag $TAG

$PERFECT_CMD designs create lidar2d=UST    camera=D455 navigation=RTAB global_planner=NavFn local_planner=Teb --template clearpath_husky --name "Husky (UST, D455, Teb)" --tag $TAG
$PERFECT_CMD designs create lidar2d=LMS111 camera=D455 navigation=RTAB global_planner=NavFn local_planner=Teb --template clearpath_husky --name "Husky (LMS1XX, D455, Teb)" --tag $TAG
$PERFECT_CMD designs create lidar3d=Puck   camera=D455 navigation=RTAB global_planner=NavFn local_planner=Teb --template clearpath_husky --name "Husky (Puck, D455, Teb)" --tag $TAG

# 2D and 3D LiDARs
$PERFECT_CMD designs create lidar2d=UST    lidar3d=Puck camera=D415 navigation=RTAB global_planner=NavFn local_planner=Dynamic --template clearpath_husky --name "Husky (UST, Puck, D415)" --tag $TAG
$PERFECT_CMD designs create lidar2d=LMS111 lidar3d=Puck camera=D415 navigation=RTAB global_planner=NavFn local_planner=Dynamic --template clearpath_husky --name "Husky (LMS1XX, Puck, D415)" --tag $TAG
$PERFECT_CMD designs create lidar2d=UST    lidar3d=Puck camera=D435 navigation=RTAB global_planner=NavFn local_planner=Dynamic --template clearpath_husky --name "Husky (UST, Puck, D435)" --tag $TAG
$PERFECT_CMD designs create lidar2d=LMS111 lidar3d=Puck camera=D435 navigation=RTAB global_planner=NavFn local_planner=Dynamic --template clearpath_husky --name "Husky (LMS1XX, Puck, D435)" --tag $TAG
$PERFECT_CMD designs create lidar2d=UST    lidar3d=Puck camera=D455 navigation=RTAB global_planner=NavFn local_planner=Dynamic --template clearpath_husky --name "Husky (UST, Puck, D455)" --tag $TAG
$PERFECT_CMD designs create lidar2d=LMS111 lidar3d=Puck camera=D455 navigation=RTAB global_planner=NavFn local_planner=Dynamic --template clearpath_husky --name "Husky (LMS1XX, Puck, D455)" --tag $TAG

$PERFECT_CMD designs create lidar2d=UST    lidar3d=Puck camera=D415 navigation=RTAB global_planner=NavFn local_planner=Teb --template clearpath_husky --name "Husky (UST, Puck, D415, Teb)" --tag $TAG
$PERFECT_CMD designs create lidar2d=LMS111 lidar3d=Puck camera=D415 navigation=RTAB global_planner=NavFn local_planner=Teb --template clearpath_husky --name "Husky (LMS1XX, Puck, D415, Teb)" --tag $TAG
$PERFECT_CMD designs create lidar2d=UST    lidar3d=Puck camera=D435 navigation=RTAB global_planner=NavFn local_planner=Teb --template clearpath_husky --name "Husky (UST, Puck, D435, Teb)" --tag $TAG
$PERFECT_CMD designs create lidar2d=LMS111 lidar3d=Puck camera=D435 navigation=RTAB global_planner=NavFn local_planner=Teb --template clearpath_husky --name "Husky (LMS1XX, Puck, D435, Teb)" --tag $TAG
$PERFECT_CMD designs create lidar2d=UST    lidar3d=Puck camera=D455 navigation=RTAB global_planner=NavFn local_planner=Teb --template clearpath_husky --name "Husky (UST, Puck, D455, Teb)" --tag $TAG
$PERFECT_CMD designs create lidar2d=LMS111 lidar3d=Puck camera=D455 navigation=RTAB global_planner=NavFn local_planner=Teb --template clearpath_husky --name "Husky (LMS1XX, Puck, D455, Teb)" --tag $TAG

# Blackfly S is not a depth camera, so we only pair it with a 3D LiDAR
$PERFECT_CMD designs create lidar3d=Puck   camera=Blackfly navigation=RTAB global_planner=NavFn local_planner=Dynamic --template clearpath_husky --name "Husky (Puck, Blackfly S)" --tag $TAG
$PERFECT_CMD designs create lidar3d=Puck   camera=Blackfly navigation=RTAB global_planner=NavFn local_planner=Teb --template clearpath_husky --name "Husky (Puck, Blackfly S, Teb)" --tag $TAG

export GAZEBO_MODEL_PATH=
export GAZEBO_MODEL_PATH=$GAZEBO_MODEL_PATH:$GAZEBO_WORLD_MINI/difficult/models
export GAZEBO_MODEL_PATH=$GAZEBO_MODEL_PATH:$GAZEBO_WORLD_MINI/medium/models
export GAZEBO_MODEL_PATH=$GAZEBO_MODEL_PATH:$GAZEBO_WORLD_MINI/easy/models

# Create environments with various start/goal positions
$PERFECT_CMD environments create_explicit "Avoid Jersey" "{\"world\": \"playpen\", \"start\": {\"x\": 0.0, \"y\": -1.0, \"z\": 0.0}, \"goal\": {\"x\": 6.0, \"y\": 3.0, \"z\": 0.0}}" --tag $TAG

$PERFECT_CMD environments create_explicit "Kashif Difficult" "{\"world\": \"kashif-difficult\", \"start\": {\"x\": 0.0, \"y\": 0.0, \"z\": 0.7}, \"goal\": {\"x\": 24.0, \"y\":   9.0, \"z\": 0.7}}" --tag $TAG
$PERFECT_CMD environments create_explicit "Kashif Medium"    "{\"world\": \"kashif-medium\",    \"start\": {\"x\": 0.0, \"y\": 0.0, \"z\": 0.7}, \"goal\": {\"x\": -2.5, \"y\": -19.0, \"z\": 0.7}}" --tag $TAG
$PERFECT_CMD environments create_explicit "Kashif Easy"      "{\"world\": \"kashif-easy\",      \"start\": {\"x\": 0.0, \"y\": 0.0, \"z\": 0.7}, \"goal\": {\"x\": -5.0, \"y\": -10.0, \"z\": 0.7}}" --tag $TAG

#$PERFECT_CMD environments create_explicit "Backrooms" "{\"world\": \"obstacle\", \"start\": {\"x\": 2.0, \"y\": 2.0, \"z\": 0.0}, \"goal\": {\"x\": 9.0, \"y\": 8.0, \"z\": 0.0}}" --tag $TAG

# Create experiments for all combinations of designs and environments that have our tag
# FIXME see comment in perfect.app.routes.experiments about assuming patterns are tags
$PERFECT_CMD experiments create $TAG $TAG --tag $TAG

# Run (enqueue) experiments that have our tag
# FIXME similar issue about patterns just being tags for now
#$PERFECT_CMD experiments run $TAG
