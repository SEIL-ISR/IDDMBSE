import json

import click
from flask import Blueprint, current_app, render_template, request

import perfect.app.routes.utils as utils
from perfect import common
from perfect.app import db, models

bp = Blueprint("environments", __name__, url_prefix="/environments")


@bp.route("/", methods=["GET", "POST"])
def home():
    if request.method == "POST":
        data = dict(request.form)  # make a copy of the ImmutableMultiDict
        template_id = int(data.pop("template_selection"))
        name = data.pop("name")
        tag = data.pop("tag")
        _ = data.pop("submit")
        # What's left in the form data should be the kwargs for the template
        kwargs = [f"{k}:={v}" for k, v in data.items()]
        print(kwargs)
        _create_from_template(template_id, kwargs, name, tag)
    environments = db.session.query(models.Environment).all()
    templates = db.session.query(models.EnvironmentTemplate).all()
    templates = [(0, "Choose Template")] + [(_t.id, _t.name) for _t in templates]
    return render_template("environments.html", environments=environments, templates=templates)


@bp.route("/get_template_args", methods=["POST"])
def get_template_args():
    data = request.get_json()
    template_id = int(data["template_id"])
    if template_id == 0:
        return json.dumps({"args": []})
    template = db.session.get(models.EnvironmentTemplate, template_id)
    return json.dumps({"args": template.get_argument_list()})


@bp.cli.command("create_templates_from_file")
@click.argument("template_path", type=click.Path(exists=False, dir_okay=False))
def create_templates_from_file(template_path):
    try:
        f = open(template_path, "r")
    except FileNotFoundError:
        current_app.logger.info(f"Template path {template_path} not found in project root. Searching in {common.PATH}")
        for path in common.PATH.rglob(template_path):
            f = open(path, "r")
            break
        else:
            raise FileNotFoundError
    templates = json.load(f)
    if not isinstance(templates, list):
        templates = [templates]
    for template in templates:
        new_template = models.EnvironmentTemplate()
        new_template.name = template["name"]
        new_template.specification = template["specification"]
        db.session.add(new_template)
        current_app.logger.info(f"Adding environment template '{new_template.name}'")
    db.session.commit()


@bp.cli.command("create_from_template")
@click.argument("template_id", type=int)
@click.argument("kwargs", nargs=-1)
@click.option("-n", "--name")
@click.option("-t", "--tag")
def create_from_template(**kwargs):
    # Coming from click, kwargs is a tuple of strings, like ("x:=1", "y:=2")
    _create_from_template(**kwargs)

def _create_from_template(template_id, kwargs, name, tag):
    kwargs = dict([kwarg.split(":=") for kwarg in kwargs])
    template = db.session.get(models.EnvironmentTemplate, template_id)
    specification = utils.fill_specification_kwargs(template.specification, kwargs)
    environment = models.Environment()
    environment.name = name or "{} ({})".format(template.name, ", ".join(f"{k}={v}" for k, v in kwargs.items()))
    environment.tag = tag
    environment.specification = json.dumps(specification)
    environment.template_id = template_id
    db.session.add(environment)
    db.session.commit()
    current_app.logger.info(f"Committed Environment {str(environment)}")

@bp.cli.command("create_explicit")
@click.argument("name")
@click.argument("json_impl")
@click.option("-t", "--tag")
def create_explicit(name, json_impl, tag):
    environment = models.Environment()
    environment.name = name
    environment.tag = tag
    environment.specification = json_impl
    db.session.add(environment)
    db.session.commit()
