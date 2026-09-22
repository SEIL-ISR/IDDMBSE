# One design, one design point, one experiment. The campaign driver
# (isaacsim/tools/range_campaign.py) runs this same sequence for a whole grid.
#
# Run it from this directory, with PERFECT_PROJECT_ROOT set to it and the
# PERFECT virtual environment active.

# Everything created here carries the same tag
TAG=range
PERFECT_CMD="python -m flask --app perfect.app"

# Reset the database
rm -rf migrations/ *.db*
$PERFECT_CMD db init
$PERFECT_CMD db migrate -m "Initial migration."
$PERFECT_CMD db upgrade

# The AGR variants
$PERFECT_CMD components load_component_implementations components.json
$PERFECT_CMD designs create "Carter v2.4" -i --name "Carter v2.4" --tag $TAG

# The design of experiments: one environment per design point
$PERFECT_CMD environments create_templates_from_file templates/contested_terrain.json
$PERFECT_CMD environments create_from_template 1 \
    obstacle_density:=0.3 max_slope_deg:=15 friction_static:=0.6 \
    friction_dynamic:=0.5 restitution:=0.1 seed:=7 duration_s:=20 \
    --name "density 0.3, slope 15, friction 0.6/0.5, seed 7" --tag $TAG

$PERFECT_CMD experiments create $TAG $TAG --tag $TAG

# Run (enqueue) the experiments that carry our tag
#$PERFECT_CMD experiments run $TAG
