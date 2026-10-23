"""MeetRoom – ระบบจองห้องประชุม (Flask + SQLite3)"""
import os

from flask import Flask

import admin
import auth
import bookings
import db
import utils


def create_app(test_config=None):
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_mapping(
        SECRET_KEY=os.environ.get("SECRET_KEY", "dev-secret-change-me"),
        DATABASE=os.path.join(app.instance_path, "meetroom.db"),
        JSON_AS_ASCII=False,
    )
    app.json.ensure_ascii = False
    if test_config:
        app.config.update(test_config)

    os.makedirs(app.instance_path, exist_ok=True)

    db.init_app(app)
    utils.register_filters(app)
    auth.init_app(app)

    app.register_blueprint(auth.bp)
    app.register_blueprint(bookings.bp)
    app.register_blueprint(admin.bp)
    return app
