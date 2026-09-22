import logging
import os

import redis
import rq
from flask import Flask
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy

from perfect.app import config

db = SQLAlchemy()
migrate = Migrate()


def create_app() -> Flask:
    app = Flask(
        __name__,
        instance_path=config.Config.PERFECT_PROJECT_ROOT,
        instance_relative_config=True,
    )
    app.config.from_object(config.Config)

    # Configure root logger
    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    formatter = logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s %(module)s.%(funcName)s:%(lineno)d - %(message)s"
    )
    ch.setFormatter(formatter)
    logger.addHandler(ch)

    app.logger = logging.getLogger("app")
    app.logger.info("Welcome to the PERFECT Application!")

    project_config_path = os.path.join(config.Config.PERFECT_PROJECT_ROOT, "config.py")
    if os.path.exists(project_config_path):
        app.config.from_pyfile(project_config_path)
    else:
        logger.warning(f"Did not find {project_config_path}. Using application defaults")

    logger.debug(app.config)

    db.init_app(app)
    migrate.init_app(app, db)

    app.redis = redis.Redis.from_url(app.config["REDIS_URL"])
    app.task_queue = rq.Queue("perfect-tasks", connection=app.redis)

    from perfect.app.routes import (
        api,
        components,
        designs,
        environments,
        main,
        experiments,
    )

    app.register_blueprint(api.bp)
    app.register_blueprint(components.bp)
    app.register_blueprint(designs.bp)
    app.register_blueprint(environments.bp)
    app.register_blueprint(main.bp)
    app.register_blueprint(experiments.bp)

    try:
        import models  # noqa: F401
    except ImportError:
        app.logger.info("No custom model module found. Using base PERFECT models")
        from perfect.app import models  # noqa: F401

    # Reduce spam
    logging.getLogger("werkzeug").setLevel(logging.WARNING)

    return app
