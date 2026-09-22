from flask import current_app
from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileRequired
from wtforms import (
    FieldList,
    FormField,
    SelectField,
    SelectMultipleField,
    StringField,
    SubmitField,
    widgets
)
from wtforms.validators import InputRequired

from perfect.app import db, models

__STANDARDS = [
    "Single Design",
    "All Combinations",
]

# FIXME Because the form is updated by submit, we can't add or remove form
# fields unless everything (including the file we would remove) validates

class EnvvarForm(FlaskForm):
    envvar = StringField("Envvar")#, validators=[InputRequired()])
    value = StringField("Value")  # Don't use InputRequired validator so that we can explicitly unset variables

class ArgForm(FlaskForm):
    arg = StringField("Launch arg")#, validators=[InputRequired()])
    value = StringField("Value")#, validators=[InputRequired()])

class FileChangeForm(FlaskForm):
    file = StringField("File")#, validators=[InputRequired()])
    keys = StringField("Keys")#, validators=[InputRequired()])
    value = StringField("Value")#, validators=[InputRequired()])

class ComponentCreateForm(FlaskForm):
    name = StringField("Name")#, validators=[InputRequired()])
    type = StringField("Type")
    envvars = FieldList(FormField(EnvvarForm))
    add_envvar = SubmitField("Add Environment Variable")
    remove_envvar = SubmitField("Remove Environment Variable")
    args = FieldList(FormField(ArgForm))
    add_arg = SubmitField("Add Launch Argument")
    remove_arg = SubmitField("Remove Launch Argument")
    file_changes = FieldList(FormField(FileChangeForm))
    add_file_change = SubmitField("Add File Change")
    remove_file_change = SubmitField("Remove File Change")
    submit = SubmitField("Save")

class ComponentLoadForm(FlaskForm):
    upload = FileField(validators=[FileRequired()])


def environment_creation_form_generator(template_args=None) -> FlaskForm:
    template_args = template_args or []
    templates = db.session.query(models.EnvironmentTemplate).all()
    template_choices = [(0, "Choose Environment template")] + [(_t.id, f"{_t.id}. {_t}") for _t in templates]
    class EnvironmentCreationForm(FlaskForm):
        name = StringField()
        tag = StringField()
        template_selection = SelectField(
            "Select template",
            choices=template_choices,
            coerce=int,
        )
        args = [StringField(arg) for arg in template_args]
    return EnvironmentCreationForm()

def experiment_creation_form_generator() -> FlaskForm:
    designs = db.session.query(models.Design).all()
    design_choices = [(_d.id, str(_d)) for _d in designs]
    environments = db.session.query(models.Environment).all()
    environment_choices = [(_e.id, str(_e)) for _e in environments]

    class DesignAndEnvironmentSelectionForm(FlaskForm):
        design_selection = SelectField(
            "Pick Design!",
            choices=design_choices,
            coerce=int,
            option_widget=widgets.RadioInput(),
            widget=widgets.ListWidget(prefix_label=False),
        )
        environment_selection = SelectField(
            "Pick Environment!",
            choices=environment_choices,
            coerce=int,
            option_widget=widgets.RadioInput(),
            widget=widgets.ListWidget(prefix_label=False),
        )
        tag = StringField()

    return DesignAndEnvironmentSelectionForm()
