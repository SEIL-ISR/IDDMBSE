import json
from datetime import datetime
from time import time
from typing import List

import redis
import rq
import sqlalchemy as sa
import sqlalchemy.orm as so
import yaml
from flask import current_app
from sqlalchemy_serializer import SerializerMixin

from perfect.app import db

design_component_table = sa.Table(
    "design_component_table",
    db.metadata,
    sa.Column("design_id", sa.ForeignKey("design.id"), primary_key=True),
    sa.Column("component_id", sa.ForeignKey("component.id"), primary_key=True),
)


class Component(db.Model, SerializerMixin):
    serialize_rules = ("-designs.components", "-implementation.component")
    id: so.Mapped[int] = so.mapped_column(primary_key=True, autoincrement=True)
    name: so.Mapped[str] = so.mapped_column(sa.String(64), nullable=False)
    type: so.Mapped[str] = so.mapped_column(sa.String(32), nullable=False)
    brand: so.Mapped[str] = so.mapped_column(sa.String(32), nullable=True)
    image: so.Mapped[str] = so.mapped_column(nullable=True)
    reference: so.Mapped[str] = so.mapped_column(nullable=True)
    description: so.Mapped[str] = so.mapped_column(nullable=True)
    # TODO specify units somehow, maybe in column/attribute names
    angular_resolution_horizontal: so.Mapped[float] = so.mapped_column(nullable=True)
    angular_resolution_vertical: so.Mapped[float] = so.mapped_column(nullable=True)
    aperture: so.Mapped[float] = so.mapped_column(nullable=True)
    channels: so.Mapped[int] = so.mapped_column(nullable=True)
    field_of_view_diagonal: so.Mapped[float] = so.mapped_column(nullable=True)
    field_of_view_horizontal: so.Mapped[float] = so.mapped_column(nullable=True)
    field_of_view_vertical_down: so.Mapped[float] = so.mapped_column(nullable=True)
    field_of_view_vertical: so.Mapped[float] = so.mapped_column(nullable=True)
    field_of_view_vertical_up: so.Mapped[float] = so.mapped_column(nullable=True)
    focal_length: so.Mapped[float] = so.mapped_column(nullable=True)
    mass: so.Mapped[float] = so.mapped_column(nullable=True)
    max_frame_rate: so.Mapped[float] = so.mapped_column(nullable=True)
    pixel_size: so.Mapped[float] = so.mapped_column(nullable=True)
    power: so.Mapped[float] = so.mapped_column(nullable=True)
    range_accuracy: so.Mapped[float] = so.mapped_column(nullable=True)
    range_max: so.Mapped[float] = so.mapped_column(nullable=True)
    resolution_horizontal: so.Mapped[float] = so.mapped_column(nullable=True)
    resolution_vertical: so.Mapped[float] = so.mapped_column(nullable=True)
    rotation_rate_max: so.Mapped[float] = so.mapped_column(nullable=True)
    rotation_rate_min: so.Mapped[float] = so.mapped_column(nullable=True)
    voltage_max: so.Mapped[float] = so.mapped_column(nullable=True)
    voltage_min: so.Mapped[float] = so.mapped_column(nullable=True)
    wavelength: so.Mapped[float] = so.mapped_column(nullable=True)
    __table_args__ = (
        sa.UniqueConstraint("name"),
    )
    implementation: so.Mapped["ComponentImplementation"] = so.relationship(back_populates="component")
    designs: so.Mapped[List["Design"]] = so.relationship(
        secondary=design_component_table,
        back_populates="components",
    )


class ComponentImplementation(db.Model, SerializerMixin):
    serialize_rules = ("-component.implementation",)
    id: so.Mapped[int] = so.mapped_column(primary_key=True, autoincrement=True)
    name: so.Mapped[str] = so.mapped_column(sa.String(64))
    type: so.Mapped[str] = so.mapped_column(sa.String(32), nullable=False)
    implementation = sa.Column(sa.types.JSON)
    __table_args__ = (
        sa.UniqueConstraint("name"),
    )
    component_id: so.Mapped[int] = so.mapped_column(sa.ForeignKey(Component.id), index=True, nullable=True)
    component: so.Mapped[Component] = so.relationship(back_populates="implementation")

    def __repr__(self):
        return f"<id={self.id} implementation={self.implementation}>"

    def __str__(self):
        return self.name or self.__repr__()

    def pretty_print_data(self):
        if self.component is not None:
            data = self.component.to_dict(rules=("-designs", "-id", "-implementation"))
            return (
                "<br>".join(f"{k}: {v}" for k, v in data.items() if v is not None)
            )
        return ""

    def pretty_print_implementation(self):
        envvars = "<br>".join(f"{_e['envvar']}={_e['value']}" for _e in self.implementation.get("envvars", []))
        launchargs = "<br>".join(f"{_l['arg']}:={_l['value']}" for _l in self.implementation.get("launchargs", []))
        filechanges = "<br>".join(_pretty_print_file_updates(_f["file"], _f["updates"]) for _f in self.implementation.get("files", []))
        return \
            (f"<h3><b><u>Environment variables</u></b></h3><p>{envvars}</p>" if envvars else "") + \
            (f"<h3><b><u>CLI arguments</u></b></h3><p>{launchargs}</p>" if launchargs else "") + \
            (filechanges if filechanges else "")

def _pretty_print_file_updates(file, updates):
    updates = f"<br>".join(f"{update['keys']}: {_pretty_print_file_update(file, update['value'])}" for update in updates)
    return f"<h3><b><u>{file}</u></b></h3><pre>{updates}</pre>"

def _pretty_print_file_update(file, update):
    if isinstance(update, str):
        return update
    if file.endswith("yaml"):
        return yaml.dump_all(update)
    raise NotImplementedError


class Design(db.Model):
    id: so.Mapped[int] = so.mapped_column(primary_key=True, autoincrement=True)
    name: so.Mapped[str] = so.mapped_column(sa.String(32), nullable=True)
    tag: so.Mapped[str] = so.mapped_column(sa.String(16), nullable=True)
    template_id: so.Mapped[str] = so.mapped_column(sa.String(16), nullable=True)
    implementation = sa.Column(sa.types.JSON)
    __table_args__ = (
        sa.UniqueConstraint("name"),
    )
    components: so.Mapped[List["Component"]] = so.relationship(
        secondary=design_component_table,
        back_populates="designs",
    )
    experiments: so.WriteOnlyMapped["Experiment"] = so.relationship(
        back_populates="design"
    )

    def __repr__(self):
        components = ", ".join(str(_c) for _c in self.components)
        return f"<id={self.id} components=[{components}]>"

    def __str__(self):
        return self.name or self.__repr__()

    def get_experiments(self):
        query = self.experiments.select().where(Experiment.design_id == self.id)
        return db.session.scalars(query)


class EnvironmentTemplate(db.Model):
    id: so.Mapped[int] = so.mapped_column(primary_key=True, autoincrement=True)
    name: so.Mapped[str] = so.mapped_column(sa.String(64), nullable=True)
    specification = sa.Column(sa.types.JSON)
    __table_args__ = (
        sa.UniqueConstraint("name"),
    )
    environments: so.WriteOnlyMapped[List["Environment"]] = so.relationship()
    def __repr__(self):
        return f"<id={self.id} specification={self.specification}>"
    def __str__(self):
        return self.name or self.__repr__()
    def get_argument_list(self):
        return list(sorted(set(self._get_arguments(self.specification))))
    @classmethod
    def _get_arguments(cls, specification):
        for v in specification.values() if type(specification) == dict else specification:
            if type(v) == dict or type(v) == list:
                yield from cls._get_arguments(v)
            elif type(v) == str and v.startswith("$"):
                yield v[1:]


class Environment(db.Model):
    id: so.Mapped[int] = so.mapped_column(primary_key=True, autoincrement=True)
    name: so.Mapped[str] = so.mapped_column(sa.String(32), nullable=True)
    tag: so.Mapped[str] = so.mapped_column(sa.String(16), nullable=True)
    specification = sa.Column(sa.types.JSON)
    __table_args__ = (
        sa.UniqueConstraint("name"),
    )
    template_id: so.Mapped[int] = so.mapped_column(sa.ForeignKey(EnvironmentTemplate.id), index=True, nullable=True)
    experiments: so.WriteOnlyMapped["Experiment"] = so.relationship(
        back_populates="environment"
    )

    def __repr__(self):
        return f"<id={self.id} specification={self.specification}>"

    def __str__(self):
        return self.name or self.__repr__()

    def pretty_print_specification(self):
        specification = json.loads(self.specification)  # FIXME self.specification is a string here, it seems, but is a dict in Components. Why?
        envvars = "<br>".join(f"{_e['envvar']}={_e['value']}" for _e in specification.get("envvars", []))
        launchargs = "<br>".join(f"{_l['arg']}:={_l['value']}" for _l in specification.get("launchargs", []))
        filechanges = "<br>".join(_pretty_print_file_updates(_f["file"], _f["updates"]) for _f in specification.get("files", []))
        on_init = "<br>".join(self._pretty_print_init(_init) for _init in specification.get("init", []))
        goal = self._pretty_print_goal(specification["goal"])
        return \
            (f"<h3><b><u>Environment variables</u></b></h3><p>{envvars}</p>" if envvars else "") + \
            (f"<h3><b><u>CLI arguments</u></b></h3><p>{launchargs}</p>" if launchargs else "") + \
            (filechanges if filechanges else "") + \
            (f"<h3><b><u>On initialization</u></b></h3><p>{on_init}</p>" if on_init else "") + \
            (f"<h3><b><u>Goal</u></b></h3><p>{goal}</p>" if goal else "")

    @staticmethod
    def _pretty_print_init(init):
        return \
            (f"<i>If {init['condition']}:</i><br>" if "condition" in init else "") + \
            (f"Publish {init['publish']['msg_type']} to {init['publish']['topic']}")

    @staticmethod
    def _pretty_print_goal(goal):
        return f"Send {goal['goal_msg']['cls']} to {goal['action_name']}"


class Experiment(db.Model):
    id: so.Mapped[int] = so.mapped_column(primary_key=True, autoincrement=True)
    design_id: so.Mapped[int] = so.mapped_column(sa.ForeignKey(Design.id), index=True)
    design: so.Mapped[Design] = so.relationship(back_populates="experiments")
    environment_id: so.Mapped[int] = so.mapped_column(sa.ForeignKey(Environment.id), index=True)
    environment: so.Mapped[Environment] = so.relationship(back_populates="experiments")
    tag: so.Mapped[str] = so.mapped_column(sa.String(16), nullable=True)
    trials: so.Mapped[List["Trial"]] = so.relationship()

    def __repr__(self):
        return f"Experiment({self.id}, {self.design_id}, {self.environment_id})"

    def new_trial(self):
        trial = Trial(experiment_id=self.id, experiment=self)
        db.session.add(trial)
        trial.run()  # commit happens here

    @property
    def last_trial_id(self):
        if not self.trials:
            return None
        return self.trials[-1].id

    @property
    def last_trial_datetime(self):
        if not self.trials:
            return None
        return self.trials[-1].datetime

    @property
    def last_trial_uri(self):
        if not self.trials:
            return None
        return self.trials[-1].uri

    @property
    def last_trial_state(self):
        if not self.trials:
            return None
        return self.trials[-1].state

    @property
    def last_trial_start_age(self):
        if not self.trials:
            return None
        return self.trials[-1].start_age


class Trial(db.Model):
    id: so.Mapped[int] = so.mapped_column(primary_key=True, autoincrement=True)
    datetime = sa.Column(sa.DateTime, default=None)
    uri: so.Mapped[str] = so.mapped_column(sa.String(32), nullable=True)
    state: so.Mapped[str] = so.mapped_column(nullable=True)
    start_age: so.Mapped[float] = so.mapped_column(nullable=True)
    sim_time: so.Mapped[float] = so.mapped_column(nullable=True)
    updates: so.WriteOnlyMapped["Update"] = so.relationship(back_populates="trial")
    cancelled_by: so.Mapped[str] = so.mapped_column(nullable=True)
    job_id: so.Mapped[str] = so.mapped_column(sa.String(36), nullable=True)
    experiment_id: so.Mapped[int] = so.mapped_column(sa.ForeignKey(Experiment.id), index=True)
    experiment: so.Mapped[Experiment] = so.relationship(back_populates="trials")

    def __repr__(self):
        return f"Trial({self.id}, {self.experiment_id})"

    def run(self):
        rq_job = current_app.task_queue.enqueue(
            "perfect.app.tasks.run_trial",
            job_timeout=300,
            kwargs=dict(
                design=self.experiment.design.implementation,
                environment=json.loads(self.experiment.environment.specification),
                trial_id=self.id,
                design_name=self.experiment.design.name,
                environment_id=self.experiment.environment_id,
            ),
        )
        self.job_id = rq_job.id
        self.cancelled_by = None
        self.datetime = datetime.now()
        self.uri = None
        self.state = None
        self.start_age = None
        current_app.logger.info(f"Enqueued job {rq_job.id} for {self}")
        db.session.commit()

    def add_update(self, data):
        update = Update(trial_id=self.id, payload_json=json.dumps(data))
        db.session.add(update)
        db.session.commit()
        return update

    def get_rq_job(self) -> rq.job.Job:
        try:
            rq_job = rq.job.Job.fetch(self.job_id, connection=current_app.redis)
        except (redis.exceptions.RedisError, rq.exceptions.NoSuchJobError) as e:
            current_app.logger.error(f"Error getting job associated with {self}: {e}")
            return None
        return rq_job


class Update(db.Model):
    id: so.Mapped[int] = so.mapped_column(primary_key=True)
    trial_id: so.Mapped[int] = so.mapped_column(
        sa.ForeignKey(Trial.id),
        index=True,
    )
    timestamp: so.Mapped[float] = so.mapped_column(index=True, default=time)
    payload_json: so.Mapped[str] = so.mapped_column(sa.Text)

    trial: so.Mapped[Trial] = so.relationship(back_populates="updates")

    def get_data(self):
        return json.loads(str(self.payload_json))
