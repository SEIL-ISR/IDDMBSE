# The 2024 SEILR1 robustness campaign, updated to the current PERFECT commands.
#
# NOT RE-RUN. The command names were changed to the ones PERFECT has today; no
# part of this was executed against a running stack when it was updated on
# 2026-09-22, so the run itself is unverified. What changed:
#
#   components load <file>              -> components load_component_implementations <file>
#   environments create <world> ...     -> environments create_templates_from_file <file>
#                                          plus environments create_from_template <id> k:=v
#   simulations create / simulations run -> experiments create / experiments run
#
# The old positional `environments create $WORLD $AX $AY $BX $BY` is gone;
# environments now come from a JSON template with named arguments. The stock
# template perfect/perfect/common/templates/nav2_operation_plans/
# navigate_from_initial_pose_to_goal_pose.json declares exactly $x_start,
# $y_start, $x_goal and $y_goal, which is what the loop below passes.
# TEMPLATE points at that file, and TEMPLATE_ID is the row the load creates
# (1 on a fresh database). `environments create_templates_from_file` first
# tries TEMPLATE as a path relative to the current directory, then, on
# FileNotFoundError, searches recursively for that filename under
# perfect/perfect/common/ (perfect.common.PATH) — see
# perfect/perfect/app/routes/environments.py. A bare filename is enough.
#
# tradesx/ddo.py emits this same sequence from a design list and a grid.

# All designs, environments, and experiments we create here will have the same tag
TAG=arglebargle
TEMPLATE=navigate_from_initial_pose_to_goal_pose.json
TEMPLATE_ID=1
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
$PERFECT_CMD designs create 1 6 10 12 --name 4234 --tag $TAG
$PERFECT_CMD designs create 4 5 9 13 --name 785 --tag $TAG
$PERFECT_CMD designs create 4 8 11 13 --name 549 --tag $TAG
$PERFECT_CMD designs create 2 6 10 13 --name 2185 --tag $TAG
$PERFECT_CMD designs create 1 5 9 12 --name 4370 --tag $TAG
$PERFECT_CMD designs create 11 --name 4 --tag $TAG
$PERFECT_CMD designs create 4 --name 512 --tag $TAG

# Load the environment template the grid below fills in
$PERFECT_CMD environments create_templates_from_file $TEMPLATE

# Create a bunch of environments for various start/end positions
# Sorry for the nested loops, but ya'know...
for AX in {0..1}
do
    for AY in {0..1}
    do
        for BX in {5..7}
        do
            for BY in {2..4}
            do
                $PERFECT_CMD environments create_from_template $TEMPLATE_ID \
                    x_start:=$AX y_start:=$AY x_goal:=$BX y_goal:=$BY \
                    --name "start $AX,$AY; goal $BX,$BY" --tag $TAG
            done
        done
    done
done

# Create experiments for all combinations of designs and environments that have our tag
# FIXME see comment in perfect.app.routes.experiments about assuming patterns are tags
$PERFECT_CMD experiments create $TAG $TAG --tag $TAG

# Run (enqueue) experiments that have our tag
# FIXME similar issue about patterns just being tags for now
$PERFECT_CMD experiments run $TAG
