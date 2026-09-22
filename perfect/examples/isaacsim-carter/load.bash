# All designs, environments, and experiments we create here will have the same tag
TAG=demo
# All Flask calls start with this
PERFECT_CMD="python -m flask --app perfect.app"

# Reset the database
rm -rf migrations/ *.db*
$PERFECT_CMD db init
$PERFECT_CMD db migrate -m "Initial migration."
$PERFECT_CMD db upgrade

$PERFECT_CMD components load_components

$PERFECT_CMD designs create planner=NavFn controller=DWB  --template carter_nova --name "NavFn, DWB" --tag $TAG
$PERFECT_CMD designs create planner="A*"  controller=DWB  --template carter_nova --name "A*, DWB" --tag $TAG
$PERFECT_CMD designs create planner=NavFn controller=MPPI --template carter_nova --name "NavFn, MPPI" --tag $TAG
$PERFECT_CMD designs create planner="A*"  controller=MPPI --template carter_nova --name "A*, MPPI" --tag $TAG

$PERFECT_CMD environments create_templates_from_file navigate_to_goal_pose.json

# Create environments with various start/goal positions
$PERFECT_CMD environments create_from_template 1 x_goal:=4.5 y_goal:=-4.5 --name "Move behind forklift" --tag $TAG

# Create experiments for all combinations of designs and environments that have our tag
# FIXME see comment in perfect.app.routes.experiments about assuming patterns are tags
$PERFECT_CMD experiments create $TAG $TAG --tag $TAG

# Run (enqueue) experiments that have our tag
# FIXME similar issue about patterns just being tags for now
#$PERFECT_CMD experiments run $TAG
