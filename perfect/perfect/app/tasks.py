import asyncio
import json
import time
from itertools import cycle

import websockets
from flask import current_app
from rq import get_current_job

from perfect.app import create_app, db, models
from perfect.experiment.experiment import TrialState

app = create_app()
app.app_context().push()


def _relay_update_to_database(trial_id: int, update: str, data):
    trial: models.Trial = db.session.get(models.Trial, trial_id)
    try:
        if update == "state":
            data = str(TrialState(data))
        setattr(trial, update, data)
    except AttributeError:
        current_app.logger.debug(f"Attribute {update} doesn't exist for Trial")
        pass
    trial.add_update(dict(
        update=update,
        trial_id=trial_id,
        data=data,
    ))

def _check_if_cancelled(trial_id):
    trial: models.Trial = db.session.get(models.Trial, trial_id)
    return trial.cancelled_by is not None

async def _delegate_to_runner(uri, design, environment, trial_id, design_name, environment_id):
    _relay_update_to_database(trial_id, "uri", uri)
    async with websockets.connect(uri) as ws:
        await ws.send(json.dumps(dict(
                op="launch",
                info=dict(
                    design=design,
                    environment=environment,
                    trial_id=trial_id,
                    design_name=design_name,
                    environment_id=environment_id,
                    config={k: v for k, v in current_app.config.items() if k != "PERMANENT_SESSION_LIFETIME"},
                ),
            )))
        try:
            async for resp in ws:
                try:
                    resp = json.loads(resp)
                    current_app.logger.info(resp)
                    if (success := resp.get("success")) is not None:
                        if success == True:
                            current_app.logger.debug(resp["comment"])
                        elif success == False:
                            current_app.logger.error(resp["comment"])
                        else:
                            current_app.logger.warning(f"Unknown success value {success}")
                    if update := resp.get("update"):
                        if update == "state":
                            data = TrialState(resp["data"])
                        else:
                            data = resp["data"]
                        current_app.logger.debug(f"Updating {update} to {data}")
                        _relay_update_to_database(trial_id, update, data)
                except Exception as e:
                    current_app.logger.error(f"Oops, bungled handling response {resp}: {e}")
        except websockets.ConnectionClosedError as e:
            current_app.logger.error(f"Oops, did something happen to the server? {e}")
        except websockets.ConnectionClosedOK:
            current_app.logger.debug("Connection closed after launch op")

async def _check_availability(uri) -> bool:
    async with websockets.connect(uri, open_timeout=current_app.config["RUNNER_CONNECT_TIMEOUT_SEC"]) as ws:
        current_app.logger.debug(f"Checking if the runner at {uri=} is already busy...")
        await ws.send(json.dumps(dict(op="info")))
        resp = await ws.recv()
        resp = json.loads(resp)
        current_app.logger.debug(resp)
        return not resp["data"]["is_running"]

async def _check_for_cancellation(uri, trial_id):
    while True:
        await asyncio.sleep(current_app.config["CHECK_CANCELLED_PERIOD_SEC"])
        if _check_if_cancelled(trial_id):
            current_app.logger.info(f"Sending cancel op to {uri} for {trial_id=}")
            async with websockets.connect(uri) as ws:
                await ws.send(json.dumps(dict(op="cancel")))
                resp = await ws.recv()
                resp = json.loads(resp)
                current_app.logger.debug(resp)
                break

async def _run_trial(uri, design, environment, trial_id, design_name, environment_id):
    delegate_task = asyncio.create_task(_delegate_to_runner(uri, design, environment, trial_id, design_name, environment_id))
    check_for_cancellation_task = asyncio.create_task(_check_for_cancellation(uri, trial_id))
    await delegate_task
    check_for_cancellation_task.cancel()

from perfect.experiment.local import main as run_trial_locally  # moving this (like with isort) breaks things, for some reason

def run_trial(design, environment, trial_id, design_name, environment_id):
    job = get_current_job()
    if current_app.config["RUN_LOCALLY"]:
        run_trial_locally(
            design_name,
            environment_name=db.session.query(models.Environment).filter(models.Environment.id == environment_id).one().name,
            trial_id=trial_id,
        )
    else:
        send_trial_to_runner(design, environment, trial_id, design_name, environment_id, job)

    trial: models.Trial = db.session.get(models.Trial, trial_id)
    trial.job_id = None
    db.session.commit()

def send_trial_to_runner(design, environment, trial_id, design_name, environment_id, job):
    current_app.logger.info(f"Job {job.id} delegating Trial {trial_id} to first available runner")
    NUM_RUNNERS = len(current_app.config["RUNNER_URIS"])
    for i, uri in cycle(enumerate(current_app.config["RUNNER_URIS"], start=1)):
        current_app.logger.info(f"Trying runner {i}/{NUM_RUNNERS} at {uri}")
        try:
            available = asyncio.run(_check_availability(uri))
        except (asyncio.exceptions.CancelledError, asyncio.exceptions.TimeoutError) as e:
            current_app.logger.error(f"Whoops, got {e.__class__.__name__}")
            available = False
        if available:
            asyncio.run(_run_trial(uri, design, environment, trial_id, design_name, environment_id))
            break
        if i == NUM_RUNNERS:
            current_app.logger.info("Tried all known runners. Pausing before cycling again")
            time.sleep(current_app.config["CYCLE_RUNNERS_PERIOD_SEC"])
    current_app.logger.debug("Done! Cleaning up job")
