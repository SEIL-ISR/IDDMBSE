"""JSON REST API for PERFECT, mounted at /api/v1.

Built for the IDDMBSE release. The HTML pages under /components, /designs,
/environments and /experiments stay exactly as they were; this blueprint is a
separate, read-mostly JSON surface over the same tables, plus two POST
endpoints that create and enqueue experiments.

There is no authentication on any of these routes. Anything that can reach the
Flask port can create and run experiments. Bind the server to localhost, or put
it behind something that does authenticate, before exposing it.

/api/v1/run is the compatibility endpoint for the SysML-to-MATLAB bridge in
sysml/workbench/bridge/. It accepts the payload those functions have always
sent and turns it into a Design, an Environment and an Experiment.
"""

import hashlib
import json

from flask import Blueprint, current_app, jsonify, request, url_for

from perfect.app import db, models
from perfect.app.routes import components as components_routes
from perfect.app.routes import designs as designs_routes
from perfect.app.routes import experiments as experiments_routes
from perfect.app.routes import utils

bp = Blueprint("api", __name__, url_prefix="/api/v1")

# Component types the bridge's sensor_update payload uses, in the order the
# design should list them.
SENSOR_TYPES = ("laser_3d", "laser_2d", "camera", "depth_camera")


# ------------------------------------------------------------------
# serialization

def _specification(environment):
    # Environment.specification is written as a JSON string by
    # environments.create_explicit and _create_from_template, but the column is
    # a JSON column, so both shapes turn up. See the FIXME in models.py.
    spec = environment.specification
    if isinstance(spec, str):
        return json.loads(spec)
    return spec


def _component_dict(component):
    d = {k: v for k, v in component.to_dict(rules=("-designs", "-implementation")).items() if v is not None}
    if component.implementation is not None:
        d["implementation"] = _component_implementation_dict(component.implementation)
    return d


def _component_implementation_dict(implementation):
    return {
        "id": implementation.id,
        "name": implementation.name,
        "type": implementation.type,
        "component_id": implementation.component_id,
        "implementation": implementation.implementation,
    }


def _design_dict(design):
    return {
        "id": design.id,
        "name": design.name,
        "tag": design.tag,
        "template_id": design.template_id,
        "implementation": design.implementation,
        "components": [{"id": c.id, "name": c.name, "type": c.type} for c in design.components],
    }


def _environment_dict(environment):
    return {
        "id": environment.id,
        "name": environment.name,
        "tag": environment.tag,
        "template_id": environment.template_id,
        "specification": _specification(environment),
    }


def _environment_template_dict(template):
    return {
        "id": template.id,
        "name": template.name,
        "specification": template.specification,
        "arguments": template.get_argument_list(),
    }


def _trial_dict(trial):
    return {
        "id": trial.id,
        "experiment_id": trial.experiment_id,
        "datetime": trial.datetime.isoformat() if trial.datetime else None,
        "uri": trial.uri,
        "state": trial.state,
        "start_age": trial.start_age,
        "sim_time": trial.sim_time,
        "cancelled_by": trial.cancelled_by,
        "job_id": trial.job_id,
    }


def _experiment_dict(experiment, detail=False):
    d = {
        "id": experiment.id,
        "tag": experiment.tag,
        "design_id": experiment.design_id,
        "environment_id": experiment.environment_id,
        "last_trial_id": experiment.last_trial_id,
        "last_trial_state": experiment.last_trial_state,
    }
    if detail:
        d["design"] = _design_dict(experiment.design)
        d["environment"] = _environment_dict(experiment.environment)
        d["trials"] = [_trial_dict(t) for t in experiment.trials]
    return d


def _status_url(experiment_id):
    return url_for("api.experiment_detail", id=experiment_id, _external=True)


# ------------------------------------------------------------------
# read-only routes

@bp.route("/components")
def components():
    rows = db.session.query(models.Component).all()
    return jsonify([_component_dict(c) for c in rows])


@bp.route("/component_implementations")
def component_implementations():
    # The library separates the implementation-agnostic Component from its
    # stack-specific ComponentImplementation. Examples such as dummy and
    # ros2-turtlebot3 have only the latter, so it needs its own route.
    rows = db.session.query(models.ComponentImplementation).all()
    return jsonify([_component_implementation_dict(r) for r in rows])


@bp.route("/designs")
def designs():
    rows = db.session.query(models.Design).all()
    return jsonify([_design_dict(d) for d in rows])


@bp.route("/designs/<int:id>")
def design_detail(id):
    design = db.session.get(models.Design, id)
    if design is None:
        return jsonify({"error": f"No design with id {id}"}), 404
    return jsonify(_design_dict(design))


@bp.route("/environments")
def environments():
    rows = db.session.query(models.Environment).all()
    return jsonify([_environment_dict(e) for e in rows])


@bp.route("/environments/<int:id>")
def environment_detail(id):
    environment = db.session.get(models.Environment, id)
    if environment is None:
        return jsonify({"error": f"No environment with id {id}"}), 404
    return jsonify(_environment_dict(environment))


@bp.route("/environment_templates")
def environment_templates():
    rows = db.session.query(models.EnvironmentTemplate).all()
    return jsonify([_environment_template_dict(t) for t in rows])


@bp.route("/experiments", methods=["GET"])
def experiments():
    rows = db.session.query(models.Experiment).all()
    return jsonify([_experiment_dict(e) for e in rows])


@bp.route("/experiments/<int:id>")
def experiment_detail(id):
    experiment = db.session.get(models.Experiment, id)
    if experiment is None:
        return jsonify({"error": f"No experiment with id {id}"}), 404
    return jsonify(_experiment_dict(experiment, detail=True))


@bp.route("/trials/<int:id>")
def trial_detail(id):
    trial = db.session.get(models.Trial, id)
    if trial is None:
        return jsonify({"error": f"No trial with id {id}"}), 404
    limit = request.args.get("updates", default=100, type=int)
    updates = (
        db.session.query(models.Update)
        .filter(models.Update.trial_id == id)
        .order_by(models.Update.timestamp)
        .limit(limit)
        .all()
    )
    d = _trial_dict(trial)
    # Unlike GET /experiments/updates, which the HTML pages poll and which
    # deletes the rows it returns, this leaves the Update rows in place.
    d["updates"] = [{"timestamp": u.timestamp, "data": u.get_data()} for u in updates]
    return jsonify(d)


# ------------------------------------------------------------------
# create the library, the designs and the environments
#
# The CLI (perfect/app/routes/components.py, designs.py, environments.py) is the
# other way to do all of this. These routes exist so that a design-space
# exploration tool can set a campaign up over HTTP without a shell on the
# server's machine. Each one reuses the CLI's own create function, and each one
# is idempotent on the name: a second POST with a name that is already in the
# table returns that row with "created": false instead of raising on the unique
# constraint. That is what makes a campaign script safe to re-run.

@bp.route("/component_implementations", methods=["POST"])
def create_component_implementations():
    body = request.get_json(silent=True)
    entries = body.get("components") if isinstance(body, dict) else body
    if not isinstance(entries, list):
        return jsonify({"error": "Body must be a list of components, or an object with a 'components' list"}), 400
    created, existing, invalid = [], [], []
    for entry in entries:
        name = entry.get("name")
        row = db.session.query(models.ComponentImplementation).filter(
            models.ComponentImplementation.name == name).first()
        if row is not None:
            existing.append(_component_implementation_dict(row))
            continue
        # _create_component validates against schema/implementation_schema.json
        # and logs the reason when it does not pass.
        if components_routes._create_component(name, entry.get("type"), entry.get("implementation")):
            row = db.session.query(models.ComponentImplementation).filter(
                models.ComponentImplementation.name == name).one()
            created.append(_component_implementation_dict(row))
        else:
            invalid.append(name)
    status = 400 if invalid and not created else 201
    return jsonify({"created": created, "existing": existing, "invalid": invalid}), status


@bp.route("/designs", methods=["POST"])
def create_design():
    body = request.get_json(silent=True) or {}
    name = body.get("name")
    if name:
        design = db.session.query(models.Design).filter(models.Design.name == name).first()
        if design is not None:
            return jsonify({"design": _design_dict(design), "created": False}), 200
    implementations = "component_implementation_ids" in body or "component_implementation_names" in body
    ids = body.get("component_implementation_ids") or body.get("component_ids") or []
    names = body.get("component_implementation_names") or body.get("component_names") or []
    if names:
        model = models.ComponentImplementation if implementations else models.Component
        rows = db.session.query(model).filter(model.name.in_(names)).all()
        by_name = {r.name: r.id for r in rows}
        missing = [n for n in names if n not in by_name]
        if missing:
            return jsonify({"error": f"No {model.__name__} named {missing}"}), 400
        ids = [by_name[n] for n in names]
    if not ids:
        return jsonify({"error": "Give component_implementation_ids, component_ids, "
                                 "component_implementation_names or component_names"}), 400
    design = designs_routes._create_design(
        {"groups": {"UNGROUPED": list(ids)}},
        user_parameters=body.get("parameters"),
        name=name,
        tag=body.get("tag"),
        implementations=implementations,
    )
    return jsonify({"design": _design_dict(design), "created": True}), 201


@bp.route("/environment_templates", methods=["POST"])
def create_environment_template():
    body = request.get_json(silent=True) or {}
    name = body.get("name")
    template = db.session.query(models.EnvironmentTemplate).filter(
        models.EnvironmentTemplate.name == name).first()
    if template is not None:
        return jsonify({"template": _environment_template_dict(template), "created": False}), 200
    specification = body.get("specification")
    if not isinstance(specification, (dict, list)):
        return jsonify({"error": "specification must be a JSON object or array"}), 400
    template = models.EnvironmentTemplate()
    template.name = name
    template.specification = specification
    db.session.add(template)
    db.session.commit()
    return jsonify({"template": _environment_template_dict(template), "created": True}), 201


@bp.route("/environments", methods=["POST"])
def create_environment():
    body = request.get_json(silent=True) or {}
    name = body.get("name")
    if name:
        environment = db.session.query(models.Environment).filter(
            models.Environment.name == name).first()
        if environment is not None:
            return jsonify({"environment": _environment_dict(environment), "created": False}), 200
    template_id = body.get("template_id")
    if template_id is not None:
        template = db.session.get(models.EnvironmentTemplate, template_id)
        if template is None:
            return jsonify({"error": f"No environment template with id {template_id}"}), 404
        try:
            # Same substitution the HTML form and the CLI use: every "$name" in
            # the template is replaced by arguments["name"].
            specification = utils.fill_specification_kwargs(template.specification, body.get("arguments") or {})
        except KeyError as e:
            return jsonify({"error": str(e)}), 400
    else:
        specification = body.get("specification")
        if not isinstance(specification, (dict, list)):
            return jsonify({"error": "Give either template_id plus arguments, or an explicit specification"}), 400
    environment = models.Environment()
    environment.name = name
    environment.tag = body.get("tag")
    # Trial.run does json.loads on this column, so it is stored as a string,
    # exactly as environments.create_explicit and _create_from_template store it.
    environment.specification = json.dumps(specification)
    environment.template_id = template_id
    db.session.add(environment)
    db.session.commit()
    return jsonify({"environment": _environment_dict(environment), "created": True}), 201


# ------------------------------------------------------------------
# create and enqueue

def _rows_by_ids_or_tag(model, body, ids_key, tag_key):
    ids = body.get(ids_key)
    if ids:
        if not isinstance(ids, list):
            ids = [ids]
        return db.session.query(model).filter(model.id.in_(ids)).all()
    tag = body.get(tag_key)
    if tag:
        return db.session.query(model).filter(model.tag.is_(tag)).all()
    return []


@bp.route("/experiments", methods=["POST"])
def create_experiments():
    body = request.get_json(silent=True) or {}
    designs_ = _rows_by_ids_or_tag(models.Design, body, "design_ids", "design_tag")
    environments_ = _rows_by_ids_or_tag(models.Environment, body, "environment_ids", "environment_tag")
    if not designs_:
        return jsonify({"error": "No design matched design_ids or design_tag"}), 400
    if not environments_:
        return jsonify({"error": "No environment matched environment_ids or environment_tag"}), 400
    tag = body.get("tag") or body.get("name")
    run = body.get("run", True)
    created = []
    for design in designs_:
        for environment in environments_:
            experiment = experiments_routes._create(design.id, environment.id, tag)
            trial_ids = []
            if run:
                experiment.new_trial()
                trial_ids = [experiment.last_trial_id]
            created.append({
                "experiment_id": experiment.id,
                "design_id": design.id,
                "environment_id": environment.id,
                "trial_ids": trial_ids,
                "status_url": _status_url(experiment.id),
            })
    return jsonify({
        "experiments": created,
        "experiment_ids": [c["experiment_id"] for c in created],
        "trial_ids": [t for c in created for t in c["trial_ids"]],
    }), 201


@bp.route("/experiments/<int:id>/run", methods=["POST"])
def run_experiment(id):
    experiment = db.session.get(models.Experiment, id)
    if experiment is None:
        return jsonify({"error": f"No experiment with id {id}"}), 404
    experiment.new_trial()
    return jsonify({
        "experiment_id": experiment.id,
        "trial_ids": [experiment.last_trial_id],
        "status_url": _status_url(experiment.id),
    }), 201


# ------------------------------------------------------------------
# bridge compatibility: POST /api/v1/run

def _library_model():
    # Prefer Component rows. Examples that create ComponentImplementation rows
    # directly (dummy, ros2-turtlebot3) have an empty Component table, and a
    # design over those has to be built with implementations=True.
    if db.session.query(models.Component).count():
        return models.Component, False
    return models.ComponentImplementation, True


def _match_by_name(model, value):
    rows = db.session.query(model).filter(model.name == value).all()
    if not rows:
        rows = db.session.query(model).filter(model.name.contains(value)).all()
    return rows[0] if rows else None


def _match_by_type_and_spec(model, type_, spec):
    rows = db.session.query(model).filter(model.type == type_).all()
    if not rows:
        return None
    for key in ("model", "name"):
        token = spec.get(key)
        if not token:
            continue
        narrowed = [r for r in rows if str(token).lower() in (r.name or "").lower()]
        if narrowed:
            rows = narrowed
            break
    rate = spec.get("update_rate")
    if rate is not None:
        narrowed = [r for r in rows if str(rate) in (r.name or "")]
        if narrowed:
            rows = narrowed
    return rows[0]


def _resolve_components(model, launch_args, sensor_update):
    """Match the bridge payload against the library. Returns (rows, report)."""
    rows = []
    report = []
    for arg in ("base_global_planner", "base_local_planner"):
        value = launch_args.get(arg)
        if not value:
            continue
        row = _match_by_name(model, value)
        report.append({"from": arg, "value": value, "matched": row.name if row else None})
        if row is not None:
            rows.append(row)
    for type_ in SENSOR_TYPES:
        spec = sensor_update.get(type_)
        if not isinstance(spec, dict):
            continue
        row = _match_by_type_and_spec(model, type_, spec)
        report.append({"from": type_, "value": spec.get("model") or spec.get("name"), "matched": row.name if row else None})
        if row is not None:
            rows.append(row)
    # Anything else in sensor_update that is not one of the four known types
    for type_, spec in sensor_update.items():
        if type_ in SENSOR_TYPES or not isinstance(spec, dict):
            continue
        row = _match_by_type_and_spec(model, type_, spec)
        report.append({"from": type_, "value": spec.get("model") or spec.get("name"), "matched": row.name if row else None})
        if row is not None:
            rows.append(row)
    return rows, report


def _design_name(rows, digest_source):
    digest = hashlib.sha1(json.dumps(digest_source, sort_keys=True).encode()).hexdigest()[:6]
    label = ", ".join(r.name for r in rows) or "no components"
    return f"{label[:24]} #{digest}"


def _match_or_create_design(rows, implementations, name, launch_file):
    design = db.session.query(models.Design).filter(models.Design.name == name).first()
    if design is not None:
        return design, False
    selection = {"groups": {"UNGROUPED": [r.id for r in rows]}}
    design = designs_routes._create_design(
        selection,
        user_parameters=None,
        name=name,
        tag="api",
        implementations=implementations,
    )
    if launch_file:
        # The bridge sends the launch file it used to drive directly. No
        # experiment class reads it yet; carry it in the design implementation
        # so it is not lost. Every consumer of a design implementation reads
        # only envvars/launchargs/files, so this entry is inert.
        design.implementation = list(design.implementation) + [{"launch_file": launch_file}]
        db.session.commit()
    return design, True


def _match_or_create_environment(domain):
    query = db.session.query(models.Environment)
    if domain:
        environment = query.filter(models.Environment.name == domain).first()
        if environment is None:
            environment = query.filter(models.Environment.name.contains(domain)).first()
        if environment is not None:
            return environment, False
    else:
        environment = query.order_by(models.Environment.id).first()
        if environment is not None:
            return environment, False
    environment = models.Environment()
    environment.name = domain or "default"
    environment.tag = "api"
    environment.specification = json.dumps({})
    db.session.add(environment)
    db.session.commit()
    return environment, True


@bp.route("/run", methods=["POST"])
def run():
    """Accept the SysML-to-MATLAB bridge payload and run it.

    Body (either or both of launch_args and sensor_update):

        {"launch_file": "<path>",
         "launch_args": {"base_global_planner": "navfn/NavfnROS",
                         "base_local_planner": "teb_local_planner/TebLocalPlannerROS",
                         "domain": "playpen"},
         "sensor_update": {"laser_3d": {"model": "vlp16", "update_rate": 15}, ...}}

    Reply: {"experiment_id": N, "trial_ids": [M], "status_url": "..."} plus the
    design, environment and a report of what each payload field matched.
    """
    body = request.get_json(silent=True) or {}
    launch_args = body.get("launch_args") or {}
    sensor_update = body.get("sensor_update") or {}
    if not isinstance(launch_args, dict) or not isinstance(sensor_update, dict):
        return jsonify({"error": "launch_args and sensor_update must be JSON objects"}), 400
    launch_file = body.get("launch_file")

    model, implementations = _library_model()
    rows, report = _resolve_components(model, launch_args, sensor_update)
    name = _design_name(rows, {"launch_args": launch_args, "sensor_update": sensor_update, "launch_file": launch_file})
    design, design_created = _match_or_create_design(rows, implementations, name, launch_file)
    environment, environment_created = _match_or_create_environment(launch_args.get("domain"))

    experiment = experiments_routes._create(design.id, environment.id, tag="api")
    experiment.new_trial()
    current_app.logger.info(f"/api/v1/run created {experiment} from {len(rows)} matched components")
    return jsonify({
        "experiment_id": experiment.id,
        "trial_ids": [experiment.last_trial_id],
        "status_url": _status_url(experiment.id),
        "design": {"id": design.id, "name": design.name, "created": design_created},
        "environment": {"id": environment.id, "name": environment.name, "created": environment_created},
        "matched": report,
        "library": model.__name__,
    }), 201
