# The tools and environments the selected stages need, checked before anything
# starts. UPPAAL and Isaac Sim are optional: without them the stages that use
# them say so and skip.

STAGE_WHEN=default
STAGE_TITLE="check the tools and environments the selected stages need"

stage_run() {
    local missing=0 verifyta tools

    need_command() {
        if command -v "$1" > /dev/null; then
            echo "ok $1"
        else
            echo "missing $1: $2"
            missing=1
        fi
    }
    need_venv() {
        if [ -d "$REPO/$1/.venv" ]; then
            echo "ok $1/.venv"
        else
            echo "missing $1/.venv: $2"
            missing=1
        fi
    }

    if [ "$DRY_RUN" = 1 ]; then
        echo "+ check uv, redis-server, redis-cli, curl, ss, python3 and the environments of" \
            "perfect, trades-x, veritas$(selected rarrt-planning && echo ", case-studies/A2-risk-sensitive-planning")$(selected conformal-calibration && echo ", case-studies/B2-conformal-perception")$(selected isaacsim-range && echo ", isaacsim/tools");" \
            "the trial interpreter $TRIAL_PYTHON; verifyta and ISAACSIM_PYTHON if set"
        return 0
    fi

    need_command uv "https://docs.astral.sh/uv/"
    need_command redis-server "install Redis"
    need_command redis-cli "install Redis"
    need_command curl "install curl"
    need_command ss "install iproute2"
    need_command python3 "install Python 3"

    need_venv perfect "cd perfect && uv venv --python 3.12 && uv pip install -e ."
    if [ -d "$PERFECT_VENV" ]; then
        if ( source "$PERFECT_VENV/bin/activate" && python -c "import perfect, flask, rq, redis" ); then
            echo "ok perfect/.venv imports perfect, flask, rq, redis"
        else
            echo "perfect/.venv cannot import perfect, flask, rq and redis: cd perfect && uv pip install -e ."
            missing=1
        fi
    fi
    need_venv trades-x "cd trades-x && uv sync"
    need_venv veritas "cd veritas && uv venv --python 3.10 && uv sync"
    selected rarrt-planning && need_venv case-studies/A2-risk-sensitive-planning \
        "cd case-studies/A2-risk-sensitive-planning && uv sync"
    selected conformal-calibration && need_venv case-studies/B2-conformal-perception \
        "cd case-studies/B2-conformal-perception && uv sync"

    if "$TRIAL_PYTHON" -c "import numpy, scipy, yaml" 2> /dev/null; then
        echo "ok trial interpreter $TRIAL_PYTHON: $("$TRIAL_PYTHON" -c "import numpy, scipy; print('numpy', numpy.__version__, 'scipy', scipy.__version__)")"
    else
        echo "the trial interpreter $TRIAL_PYTHON cannot import numpy, scipy and yaml; point PIPELINE_TRIAL_PYTHON at one that can"
        missing=1
    fi

    local isaac="not needed"
    if selected isaacsim-range; then
        need_venv isaacsim/tools "cd isaacsim/tools && uv sync"
        if [ ! -f "$REPO/isaacsim/range/terrain/heightmap.npz" ]; then
            echo "missing isaacsim/range/terrain/heightmap.npz: see isaacsim/README.md for the fetch and build steps"
            missing=1
        fi
        if [ -z "${ISAACSIM_PYTHON:-}" ]; then
            isaac="ISAACSIM_PYTHON not set, the range stage will skip"
        elif [ -x "$ISAACSIM_PYTHON" ]; then
            isaac="Isaac Sim at ISAACSIM_PYTHON"
        else
            echo "ISAACSIM_PYTHON is set but $ISAACSIM_PYTHON is not executable"
            missing=1
        fi
        echo "$isaac"
    fi

    local uppaal="verifyta not found, the UPPAAL stage writes the models and skips the check"
    if verifyta="$(find_verifyta)"; then
        uppaal="$("$verifyta" -v 2>&1 | head -1 | sed 's/\x1b\[[0-9;]*m//g')"
    fi
    echo "UPPAAL: $uppaal"

    [ "$missing" = 0 ] || return 1
    tools="uv $(uv --version | awk '{ print $2 }'), $(redis-server --version | awk '{ print $3 }' | tr -d 'v=' | sed 's/^/Redis /')"
    headline "$tools; UPPAAL: $uppaal; Isaac Sim: $isaac"
}
