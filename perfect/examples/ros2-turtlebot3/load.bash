# All designs, environments, and experiments we create here will have the same tag
TAG=demo
# All Flask calls start with this
PERFECT_CMD="python -m flask --app perfect.app"

# Reset the database
rm -rf migrations/ *.db*
$PERFECT_CMD db init
$PERFECT_CMD db migrate -m "Initial migration."
$PERFECT_CMD db upgrade

# Load the components library
$PERFECT_CMD components load_component_implementations components.json

# Create some hand-picked designs
$PERFECT_CMD designs create Waffle -i --name "Waffle (Nav2 defaults)" --tag $TAG
$PERFECT_CMD designs create Burger -i --name "Burger (Nav2 defaults)" --tag $TAG
$PERFECT_CMD designs create Waffle Consistent -i --name "Waffle Consistent Replanning" --tag $TAG
$PERFECT_CMD designs create Waffle Recovery -i --name "Waffle Replanning and Recovery" --tag $TAG
$PERFECT_CMD designs create Burger Consistent -i --name "Burger Consistent Replanning" --tag $TAG
$PERFECT_CMD designs create Burger Recovery -i --name "Burger Replanning and Recovery" --tag $TAG
$PERFECT_CMD designs create Waffle Consistent SLAM -i --name "Waffle Consistent Replanning, SLAM" --tag $TAG
$PERFECT_CMD designs create Waffle Recovery SLAM -i --name "Waffle Replanning and Recovery, SLAM" --tag $TAG
$PERFECT_CMD designs create Burger Consistent SLAM -i --name "Burger Consistent Replanning, SLAM" --tag $TAG
$PERFECT_CMD designs create Burger Recovery SLAM -i --name "Burger Replanning and Recovery, SLAM" --tag $TAG

$PERFECT_CMD environments create_templates_from_file navigate_from_initial_pose_to_goal_pose.json

# Create environments with various start/goal positions
$PERFECT_CMD environments create_from_template 1 x_start:=-2.0 y_start:=-0.5 x_goal:=-0.5 y_goal:=-0.5 --name "S to C" --tag $TAG
$PERFECT_CMD environments create_from_template 1 x_start:=-2.0 y_start:=-0.5  x_goal:=0.5 y_goal:=-0.5 --name "S to D" --tag $TAG
$PERFECT_CMD environments create_from_template 1 x_start:=-2.0 y_start:=-0.5 x_goal:=-0.5  y_goal:=0.5 --name "S to B" --tag $TAG
$PERFECT_CMD environments create_from_template 1 x_start:=-2.0 y_start:=-0.5  x_goal:=0.5  y_goal:=0.5 --name "S to A" --tag $TAG
$PERFECT_CMD environments create_from_template 1 x_start:=-0.5 y_start:=-0.5  x_goal:=0.5  y_goal:=0.5 --name "C to A" --tag $TAG

# Create experiments for all combinations of designs and environments that have our tag
# FIXME see comment in perfect.app.routes.experiments about assuming patterns are tags
$PERFECT_CMD experiments create $TAG $TAG --tag $TAG

# Run (enqueue) experiments that have our tag
# FIXME similar issue about patterns just being tags for now
#$PERFECT_CMD experiments run $TAG
