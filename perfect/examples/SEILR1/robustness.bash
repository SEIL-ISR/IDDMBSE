# All designs, environments, and experiments we create here will have the same tag
TAG=arglebargle
WORLD=playpen
# All Flask calls start with this
PERFECT_CMD="python -m flask --app perfect.app"

# Reset the database
rm -rf migrations/ *.db*
$PERFECT_CMD db init
$PERFECT_CMD db migrate -m "Initial migration."
$PERFECT_CMD db upgrade

# Load the components library
$PERFECT_CMD components load components.json

# Create some hand-picked designs
$PERFECT_CMD designs create 1 6 10 12 --name 4234 --tag $TAG
$PERFECT_CMD designs create 4 5 9 13 --name 785 --tag $TAG
$PERFECT_CMD designs create 4 8 11 13 --name 549 --tag $TAG
$PERFECT_CMD designs create 2 6 10 13 --name 2185 --tag $TAG
$PERFECT_CMD designs create 1 5 9 12 --name 4370 --tag $TAG
$PERFECT_CMD designs create 11 --name 4 --tag $TAG
$PERFECT_CMD designs create 4 --name 512 --tag $TAG

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
                $PERFECT_CMD environments create $WORLD $AX $AY $BX $BY --tag $TAG
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
