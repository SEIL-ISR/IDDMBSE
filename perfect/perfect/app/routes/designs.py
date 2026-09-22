import json
import os
import pprint
from collections import defaultdict
from functools import partial
from typing import Dict, List, Optional, Union

import click
import sqlalchemy as sa
from flask import Blueprint, current_app, redirect, render_template, request
from sqlalchemy.orm.exc import NoResultFound

from perfect.app import db, models

bp = Blueprint("designs", __name__, url_prefix="/designs")


@bp.route("/", methods=["GET", "POST"])
def home():
    designs = db.session.query(models.Design).all()
    return render_template("designs.html", designs=designs, templates=_get_available_templates())


@bp.route("robot/<template_name>", methods=["GET", "POST"])
def design_from_template(template_name: str):
    if request.method == "POST":
        anonymous = []  # TODO
        groups = defaultdict(list)
        name = request.form["name"]
        user_parameters = defaultdict(lambda: defaultdict(dict))
        for k, v in request.form.items():
            match k.split('-'):
                case ["name"]:
                    continue
                case [g, _, "select"]:
                    # Component selection
                    v = int(v)
                    if v == 0:
                        continue
                    groups[g].append(v)
                case [g, i, c, "parameter", parameter]:
                    i = int(i)
                    v =_coerce(v, (int, float, str))
                    user_parameters[g][i-1]['$'+parameter] = v
        component_selection = dict(anonymous=anonymous, groups=groups)
        try:
            _create_design(component_selection, user_parameters, name=name, template_name=template_name)
        except ValueError:
            return "oops"  # TODO
        return redirect("/designs")
    template_path = os.path.join(current_app.config["PERFECT_PROJECT_ROOT"], "templates", f"{template_name}.json")
    if not os.path.exists(template_path):
        return f"{template_path} does not exist"
    template = json.load(open(template_path, "r"))
    implemented_components = db.session.query(models.Component).filter(models.Component.implementation != None).all()
    implemented_components = {c.id: {k: v for k, v in c.to_dict(rules=("-designs", "-id")).items() if v is not None} for c in implemented_components}
    return render_template("create_design_from_template.html", template=template, components=implemented_components)


@bp.route("status/<id>")
def status(id: int):
    design = db.first_or_404(sa.select(models.Design).where(models.Design.id == id))
    return render_template("status.html", design=design)


@bp.cli.command("list")
def list_designs():
    rows = db.session.query(models.Design).all()
    click.echo(pprint.pformat(rows))


@bp.cli.command("create")
@click.argument("components", nargs=-1, type=str)
@click.option("-n", "--name", type=str)
@click.option("-t", "--tag", type=str)
@click.option("-v", "--template", "template_name", type=str)
@click.option("-i", "--implementations", is_flag=True, show_default=True, default=False, help="Query for component implementations")
@click.option("-d", "--defaults", is_flag=True, show_default=True, default=True, help="Fill groups with defaults when underspecified (not implemented)")
@click.option("-p", "--parameters", "user_parameters", type=str, help="JSON-formatted specifications of parameters per component per group")
def create_design(components: List[str], name: str, tag: str, template_name: str, implementations: bool, defaults: bool, user_parameters: str):
    user_parameters = json.loads(user_parameters) if user_parameters else None
    if not defaults:
        raise NotImplementedError  # TODO
    groups = defaultdict(list)
    for c in components:
        try:
            group, kwarg_c = c.split("=")
            groups[group].append(_get_component_id(kwarg_c, implementations))
        except ValueError:
            pass
        else:
            continue
        try:
            component_id = _get_component_id(c, implementations)
        except ValueError:
            print(f"Failed to parse or find component '{c}'. Aborting")
            return
        groups["UNGROUPED"].append(component_id)
    component_selection = dict(groups=groups)
    try:
        return _create_design(component_selection, user_parameters, name, tag, template_name, implementations, defaults)
    except ValueError:
        print(f"Validation failed")


def _get_component_id(c: Union[int, str], impl=False) -> int:
    model = models.ComponentImplementation if impl else models.Component
    model_str = "component implementation" if impl else "component"
    # TODO: case-insensitivity
    try:
        # TODO: check that it exists
        return int(c)
    except ValueError:
        pass
    try:
        q = db.session.query(model.id, model.name).filter(model.name.is_(c)).one()
        return q[0]
    except NoResultFound:
        print(f"Warning: no {model_str} name exactly matches '{c}'")
    q = db.session.query(model.id, model.name).filter(model.name.contains(c)).all()
    if len(q) == 0:
        print(f"Error: no {model_str} name contains '{c}'")
        raise ValueError
    if len(q) > 1:
        print(f"Warning: multiple {model_str} names contain '{c}'. Taking the first one of {[_c[1] for _c in q]}")
    return q[0][0]


def _create_design(component_selection: Union[Dict, List], user_parameters, name=None, tag=None, template_name=None, implementations=False, defaults=False):
    # WARNING: a design should be defined by ComponentImplementations only if there do not exist underlying Components.
    #  This may be the case if ComponentImplementations are created directly (e.g., in the ros2-turtlebot example) (i.e., not derived from Components, such as in the ros1-clearpath-husky example)
    #  Otherwise, this is discouraged, and there will be no relation from Designs back to Components or ComponentImplementations
    model = models.ComponentImplementation if implementations else models.Component
    template = _open_template(template_name) if template_name else None
    if isinstance(component_selection, dict):
        component_ids = []
        for _, group in component_selection["groups"].items():
            if isinstance(group, list):
                component_ids = component_ids + group
            else:
                component_ids = component_ids + [group]
    else:
        component_ids = component_selection
    components = (
        db.session.query(model)
        .filter(model.id.in_(component_ids))
        .all()
    )
    if template:
        component_types = dict(db.session.query(model.id, model.type).all())
        if not _validated_against_template(component_selection, component_types, template):
            raise ValueError  #FIXME make better
    design_implementation = _get_implementation_from_selection(component_selection, implementations, template, user_parameters=user_parameters)
    design = models.Design()
    if not implementations:
        # WARNING: see above
        design.components.extend(components)
    if name:
        design.name = name
    if tag:
        design.tag = tag
    if template:
        design.template_id = template["name"]
        design.implementation = design_implementation
    else:
        # FIXME can maybe be simplified
        design.implementation = design_implementation
    db.session.add(design)
    db.session.commit()
    current_app.logger.info(f"Committed Design {repr(design)}")
    return design


def _validated_against_template(component_selection, component_types, template) -> bool:
    valid = True
    groups_types_counts = defaultdict(lambda: defaultdict(int))  # TODO need to use this when assumption mentioned below is lifted
    for group, ids in component_selection["groups"].items():
        for _id in ids:
            groups_types_counts[group][component_types[_id]] += 1
    for template_group in template["components"]:
        group_id, group_name = template_group["id"], template_group["name"]
        selection_group = component_selection["groups"][group_id]
        n = len(selection_group)  # TODO: assuming that types are valid for now
        if template_group.get("minimum", n) > n:
            print(f"Too few components in group {group_id}. Require at least {template_group['minimum']} of types {template_group['component_types']}")
            valid = False
        if template_group.get("maximum", 0) < n:
            print(f"Too many components in group {group_id}. Require no more than {template_group['maximum']} of types {template_group['component_types']}")
            valid = False
    return valid


def _get_implementation_from_selection(component_selections, implementations=False, template=None, user_parameters=None) -> List[Dict]:
    user_parameters = user_parameters or {}
    if isinstance(component_selections, list):
        component_selections = {"groups": {"UNGROUPED": component_selections}}
    design_implementation = defaultdict(list)
    for group_id, grouped_components in component_selections["groups"].items():
        group_user_parameters = user_parameters.get(group_id, {})
        for i, grouped_component_id in enumerate(grouped_components):
            group_component_user_parameters = group_user_parameters.get(i) or group_user_parameters.get(str(i))
            group_component_parameters = _get_template_group_default_parameters(template, group_id, i)
            if group_component_user_parameters:
                group_component_parameters.update(group_component_user_parameters)
            group_component_parameters = _interparameter_substitution(group_component_parameters, i)
            group_component_parameters["$i"] = i  # TODO this might come from the UI (i.e., user_parameters)
            filter_attr = models.ComponentImplementation.id if implementations else models.ComponentImplementation.component_id
            component_implementation: models.ComponentImplementation = db.session.query(models.ComponentImplementation).filter(filter_attr == grouped_component_id).one()
            component_implementation = component_implementation.implementation
            parameters = {"$"+p["name"]: p["default"] for p in component_implementation["parameters"]}
            parameters.update(group_component_parameters)
            component_implementation = _apply_parameters_to_component_implementation(component_implementation, parameters)
            design_implementation[group_id].append(component_implementation)
    # Collapse the groups of component implementations into the structure that Experiment expects
    design_implementation = [
        {k: v for k, v in group_member.items() if k != "parameters"}
        for group_members in design_implementation.values()
        for group_member in group_members
    ]
    return design_implementation


def _apply_recursive(func, obj):
    if isinstance(obj, dict):
        return {k: _apply_recursive(func, v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_apply_recursive(func, elem) for elem in obj]
    else:
        return func(obj)

def _substitute_all(s, parameters):
    for k, v in parameters.items():
        if not isinstance(s, str):
            return s
        s = s.replace(k, str(v))
        s = _coerce(s, (int, float, str))
    return s

def _apply_parameters_to_component_implementation(component_implementation, parameters):
    return _apply_recursive(partial(_substitute_all, parameters=parameters), component_implementation)


def _interparameter_substitution(parameters: dict, i: int):
    # TODO handle parameters other than the index i
    return {
        k: v.replace("$i", str(i)) if isinstance(v, str) else v for k, v in parameters.items()
    }


def _get_template_group_default_parameters(template, group_id, i):
    if template:
        for group in template["components"]:
            if group["id"] == group_id:
                if i >= len(group["implementation_parameters"]):
                    break
                return group["implementation_parameters"][i]
    return {}


def _open_template(template_name: str) -> dict:
    template_path = os.path.join(current_app.config["PERFECT_PROJECT_ROOT"], "templates", f"{template_name}.json")
    if not os.path.exists(template_path):
        raise FileNotFoundError(f"{template_path} does not exist")
    template = json.load(open(template_path, "r"))
    return template


# This is just for testing, e.g., in ros2-clearpath/experiment.py::main
def get_default_robot_design_implementation(template_name):
    template = _open_template(template_name)
    design_implementation = []
    for group in template["components"]:
        for i, (default_name, group_parameters) in enumerate(zip(group["defaults"], group["implementation_parameters"])):
            if not default_name:
                continue
            try:
                default_implementation: models.ComponentImplementation = db.session.query(models.ComponentImplementation).filter(models.ComponentImplementation.name == default_name).one()
            except sa.exc.NoResultFound:
                print(f"Didn't find default component named '{default_name}'")
                continue
            parameters = {"$"+p["name"]: p["default"] for p in default_implementation.implementation["parameters"]}
            parameters.update(group_parameters)
            parameters = _interparameter_substitution(parameters, i)
            parameters["$i"] = i
            applied_component_implementation = _apply_parameters_to_component_implementation(
                default_implementation.implementation,
                parameters=parameters
            )
            applied_component_implementation.pop("parameters")
            design_implementation.append(applied_component_implementation)
    return design_implementation


@bp.cli.command("run")
@click.argument("id")
def run_cli(id: int):
    design = db.session.get(models.Design, id)
    experiment: models.Experiment = design.add_simulation()  # FIXME
    experiment.run()
    db.session.commit()


def _get_available_templates():
    template_dir = os.path.join(current_app.config["PERFECT_PROJECT_ROOT"], "templates")
    try:
        templates = {
            json.load(open(os.path.join(template_dir, f), "r"))["name"]: f[:-5] for f in os.listdir(template_dir) if f.endswith(".json")
        }
    except FileNotFoundError:
        return {}
    return templates

def _get_matching_design(component_names) -> Optional[models.Design]:
    components = db.session.query(models.Component).filter(models.Component.name.in_(component_names)).all()
    q = db.session.query(models.Design)
    for c in components:
        # TODO Is there a better way to do this? The number of stacked filters ought to be no more than ~10
        q = q.filter(models.Design.components.contains(c))
    for d in q.all():
        if len(d.components) == len(component_names):
            return d
    return None

def match_or_create(template_name: str, component_selection_by_name: Dict[str, str]) -> models.Design:
    # component_selection_by_name should be of the form {"lidar3d": "Puck", ...}
    design = _get_matching_design(component_selection_by_name.values())
    if design is not None:
        return design
    component_selection = {
        g: [db.session.query(models.Component).filter(models.Component.name.contains(n)).one().id for n in (names if isinstance(names, list) else [names])] for g, names in component_selection_by_name.items()
    }
    return _create_design(dict(groups=component_selection), name=",".join(component_selection_by_name.values()), template_name=template_name)

def _coerce(v, types=(int, float, str)):
    for t in types:
        try:
            return t(v)
        except ValueError:
            pass
    raise ValueError(f"{t} can't be coerced into any of {types}")
