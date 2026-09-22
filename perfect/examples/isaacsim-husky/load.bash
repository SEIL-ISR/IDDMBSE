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
