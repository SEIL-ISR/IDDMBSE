import importlib
import json
import os
import sys

from flask import Config

from perfect.app import config as default_config
from perfect.app import create_app, db, models
from perfect.app.tasks import _relay_update_to_database
from perfect.experiment.experiment import (
    BaseExperiment,
    mock_relay_update_callback,
    mock_stopping_callback
)


async def _relay_update_to_database_async(update: str, data, trial_id: int):
    try:
        _relay_update_to_database(trial_id, update, data)
    except RuntimeError:
        print(f"OOPS: tried to update {update}")

def main(design_name, environment_name, trial_id=None):
    config = Config(os.path.curdir)
    config.from_object(default_config.Config)
    config.from_pyfile("config.py")

    app = create_app()
    with app.app_context():
        design: models.Design = db.session.query(models.Design).filter(models.Design.name == design_name).one()
        environment: models.Environment = db.session.query(models.Environment).filter(models.Environment.name == environment_name).one()

    sys.path.insert(1, app.config["PERFECT_PROJECT_ROOT"])
    exp_cls: type[BaseExperiment] = importlib.import_module("experiment").Experiment

    if trial_id is not None:
        _relay_update_to_database(trial_id, "uri", "localhost")
    exp_cls.launch(
        design=design.implementation,
        environment=json.loads(environment.specification),
        config=config,
        relay_update_callback=mock_relay_update_callback if trial_id is None else _relay_update_to_database_async,
        stopping_callback=mock_stopping_callback,
        trial_id=trial_id,
    )


if __name__ == "__main__":
    print(sys.argv)
    design_name = sys.argv[1]
    environment_name = sys.argv[2]
    try:
        trial_id = int(sys.argv[3])
    except IndexError:
        trial_id = None
    main(design_name, environment_name, trial_id)
