import json
import os
import pathlib
from collections import defaultdict
from typing import Dict, Union

import click
import jsonschema
import sqlalchemy as sa
from flask import (
    Blueprint,
    current_app,
    redirect,
    render_template,
    request,
    url_for
)

import perfect.app.routes.utils as utils
from perfect import common
from perfect.app import db, forms, models

bp = Blueprint("components", __name__, url_prefix="/components")


@bp.route("/", methods=["GET", "POST"])
def home():
    form = forms.ComponentLoadForm()
    if form.validate_on_submit():
        _load_component_implementations(form.upload.data.filename)
    components = db.session.query(models.ComponentImplementation).all()
    return render_template("components.html", components=components, form=form)


@bp.route("/create_implementation", methods=["GET", "POST"])
def create_implementation():
    form = forms.ComponentCreateForm()
    if form.add_envvar.data:
        form.envvars.append_entry(None)
    elif form.remove_envvar.data:
        form.envvars.pop_entry()
    elif form.add_arg.data:
        form.args.append_entry(None)
    elif form.remove_arg.data:
        form.args.pop_entry()
    elif form.add_file_change.data:
        form.file_changes.append_entry(None)
    elif form.remove_file_change.data:
        form.file_changes.pop_entry()
    elif form.submit.data:#form.validate_on_submit():  #FIXME csrf_token missing in entries in envvars, args, and file_changes
        implementation = _create_implementation_from_form(form)
        if _create_component(
            name=form.name.data,
            type=form.type.data,
            implementation=implementation,
        ):
            return redirect(url_for("components.home"))
    if form.errors:
        current_app.logger.error(form.errors)
    return render_template("create_component.html", form=form)


def _create_component(name, type, implementation: Union[Dict, str]):
    if isinstance(implementation, str):
        try:
            implementation = json.loads(implementation)
        except json.decoder.JSONDecodeError as e:
            current_app.logger.error(e)
            return False
    try:
        jsonschema.validate(implementation, schema=json.load(open(f"{os.path.dirname(os.path.realpath(__file__))}/../schema/implementation_schema.json", "r")))  # FIXME yuck
    except jsonschema.exceptions.ValidationError as e:
        current_app.logger.error(e)
        return False
    db.session.execute(
        sa.insert(models.ComponentImplementation),
        dict(name=name, type=type, implementation=implementation)
    )
    db.session.commit()
    current_app.logger.info("Commited component")
    return True


def _load_component_implementations(filepath):
    components = json.load(open(filepath, "r"))
    valid_components = []
    num_invalid = 0
    for component in components:
        try:
            jsonschema.validate(component["implementation"], schema=json.load(open(f"{os.path.dirname(os.path.realpath(__file__))}/../schema/implementation_schema.json", "r")))  # FIXME yuck
        except KeyError:
            current_app.logger.error(f"Missing 'implementation' in {component=}")
            num_invalid += 1
        except jsonschema.exceptions.ValidationError as e:
            current_app.logger.error(e)
            num_invalid += 1
        else:
            valid_components.append(component)
    db.session.execute(
        sa.insert(models.ComponentImplementation),
        valid_components,
    )
    db.session.commit()
    current_app.logger.info(
        f"Committed {len(valid_components)} Components from {filepath}"
        + (f". {num_invalid} were invalid" if num_invalid else "")
    )


def _create_implementation_from_form(form):
    spec = {}
    if form.envvars:
        spec.update({"envvars":
            [{"envvar": ev.envvar.data, "value": ev.value.data} for ev in form.envvars]
        })
    if form.args:
        spec.update({"launchargs":
            [{"arg": arg.arg.data, "value": arg.value.data} for arg in form.args]
        })
    if form.file_changes:
        changes_by_file = defaultdict(list)
        for c in form.file_changes:
            changes_by_file[c.file.data].append({
                "keys": c.keys.data,
                "value": c.value.data,
            })
        spec.update({"files":
            [{"file": f, "updates": c} for f, c in changes_by_file.items()]
        })
    return spec


@bp.cli.command("create")
@click.argument("name")
@click.argument("type")
@click.argument("implementation")
def create_component(**kwargs):
    _create_component(**kwargs)


@bp.cli.command("load_component_implementations")
@click.argument("filepath")
def load_component_implementations(filepath):
    _load_component_implementations(filepath)


@bp.cli.command("load_components")
def load_components():
    _load_components(common.PATH.joinpath("components").rglob("*.json"))


def _load_components(filepaths):
    for filepath in filepaths:
        components = json.load(open(filepath, "r"))
        for component in components:
            try:
                db.session.execute(
                    sa.insert(models.Component),
                    component,
                )
            except sa.exc.IntegrityError:
                print(f"There already exists a sensor named '{component['name']}'")
    db.session.commit()
    try:
        # The current working directory should be $PERFECT_PROJECT_ROOT
        from impl import convert  # type: ignore
    except ImportError:
        print("No impl.convert found. Component implementations table will be empty")
    else:
        components = db.session.query(models.Component).filter(models.Component.implementation == None).all()
        implementations = []
        for sensor in components:
            try:
                sensor = sensor.__dict__
                implementation = convert(sensor)
                implementation["component_id"] = sensor["id"]
                implementations.append(implementation)
            except NotImplementedError:
                print(f"This PERFECT Project cannot implement {sensor['brand']} {sensor['name']}")
            else:
                print(f"Got implementation of {implementation['name']}")
        if implementations:
            db.session.execute(
                sa.insert(models.ComponentImplementation),
                implementations,
            )
            db.session.commit()
    try:
        # The current working directory should be $PERFECT_PROJECT_ROOT
        from impl import create  # type: ignore
    except ImportError:
        print("No impl.create found")
    else:
        if implementations := list(create()):
            db.session.execute(
                sa.insert(models.ComponentImplementation),
                implementations,
            )
            db.session.commit()
