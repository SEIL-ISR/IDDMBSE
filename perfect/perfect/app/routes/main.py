from flask import Blueprint, current_app, render_template

bp = Blueprint("main", __name__)


@bp.route("/")
def home():
    return render_template("home.html", config=current_app.config)
