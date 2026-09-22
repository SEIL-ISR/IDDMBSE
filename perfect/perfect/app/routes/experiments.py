import asyncio
import json
from itertools import product
from time import time

import click
import sqlalchemy as sa
import websockets
from flask import (
    Blueprint,
    current_app,
    redirect,
    render_template,
    request,
    url_for
)

from perfect.app import db, forms, models
from perfect.app.routes import designs

bp = Blueprint("experiments", __name__, url_prefix="/experiments")


@bp.route("/", methods=["GET", "POST"])
def home():
    form = forms.experiment_creation_form_generator()
    if form.validate_on_submit():
        _create(form.design_selection.data, form.environment_selection.data)
    experiments = db.session.query(models.Experiment).all()
    return render_template("experiments.html", experiments=experiments, form=form)


@bp.route("/<id>", methods=["GET"])
def details(id: int):
    experiment = db.session.get(models.Experiment, id)
    return render_template("experiment_details.html", experiment=experiment)


def _create(design_id: int, environment_id: int, tag=None):
    design: models.Design = db.session.get(models.Design, design_id)
    environment: models.Environment = db.session.get(models.Environment, environment_id)
    experiment = models.Experiment(
        design_id=design_id,
        design=design,
        environment_id=environment_id,
        environment=environment,
        tag=tag,
    )
    db.session.add(experiment)
    db.session.commit()
    current_app.logger.info(f"Committed {experiment}")


@bp.route("run/<id>")
def run(id: int):
    experiment: models.Experiment = db.session.get(models.Experiment, id)
    experiment.new_trial()
    return redirect(url_for("experiments.home"))


@bp.route("updates")
def updates():
    now = time()
    updates = db.session.query(models.Update).where(models.Update.timestamp < now).all()
    updates_json = [
        {
            "data": update.get_data(),
        }
        for update in updates
    ]
    db.session.execute(sa.delete(models.Update).where(models.Update.timestamp < now))
    db.session.commit()
    return updates_json


@bp.route("cancel/<id>")
def cancel(id: int):
    reason = "user"  # TODO
    experiment: models.Experiment = db.session.get(models.Experiment, id)
    trial: models.Trial = db.session.get(models.Trial, experiment.last_trial_id)
    trial.cancelled_by = reason
    db.session.commit()
    return redirect(url_for("experiments.home"))


@bp.cli.command("create")
@click.argument("design_pattern")
@click.argument("environment_pattern")
@click.option("-t", "--tag")
def create(design_pattern, environment_pattern, tag):
    # FIXME for now just assume the patterns are tags
    designs = (
        db.session.query(models.Design)
        .filter(models.Design.tag.is_(design_pattern))
        .all()
    )
    environments = (
        db.session.query(models.Environment)
        .filter(models.Environment.tag.is_(environment_pattern))
        .all()
    )
    print(
        f"Patterns matched {len(designs)} designs and {len(environments)} environments, so {len(designs)*len(environments)} experiments total"
    )
    for d, e in product(designs, environments):
        experiment = models.Experiment(
            design_id=d.id, design=d, environment_id=e.id, environment=e, tag=tag
        )
        db.session.add(experiment)
    db.session.commit()


@bp.cli.command("run")
@click.argument("experiment_pattern")
def run_many(experiment_pattern):
    experiments = (
        db.session.query(models.Experiment)
        .filter(models.Experiment.tag.is_(experiment_pattern))
        .all()
    )
    for exp in experiments:
        exp.new_trial()
    db.session.commit()


# TODO: consider moving this stuff into a separate file, maybe runners.py?
# TODO: also, this needs validation and error-handling
@bp.route("observe/<id>/<topic>")
def observe(id: int, topic: str):
    return _observe(id, topic)


@bp.cli.command("echo")
@click.argument("experiment_id")
@click.argument("topic")
def echo(experiment_id: int, topic: str):
    print(_observe(experiment_id, topic))


def _observe(id, topic):
    experiment: models.Experiment = db.session.get(models.Experiment, id)
    runner_uri = experiment.last_run_uri
    results = asyncio.run(_get_last_msg(runner_uri, topic))
    return json.dumps(results)


async def _get_last_msg(uri, topic):
    results = []
    async with websockets.connect(uri) as ws:
        await ws.send(json.dumps(dict(op="get_last_msg", info=dict(topic=topic))))
        try:
            async for resp in ws:
                results.append(json.loads(resp))
        except websockets.ConnectionClosedError as e:
            print(f"Oops, did something happen to the server? Got {e}")
    return results


#  curl localhost:5000/experiments/run_locally -d '{"components":{"lidar3d":"VLP-16","lidar2d":"LMS151","camera":"D435","global_planner":"NavFn","local_planner":"Teb"},"environment":"Playpen"}'
@bp.route("run_locally", methods=["GET", "POST"])
def run_locally():
    request.get_data()
    data = request.data.decode("utf-8")
    data = json.loads(data)
    design = designs.match_or_create(data["template"], data["components"])
    environment_name = data["environment"]
    import subprocess
    p = subprocess.Popen([
        "python",
        "-m",
        "perfect.experiment.local",
        design.name,
        environment_name,
    ])
    p.wait()
    return {"result": "done"}
