import os

from flask import Flask
from jinja2 import StrictUndefined

from . import filters
from .db import db, db_setup
from .views import routes

DEFAULT_DATA_DIR = os.path.join(os.path.dirname(__file__), 'data')

def create_app(db_uri, datadir=DEFAULT_DATA_DIR, echo=True):
    app = Flask(__name__)
    app.config.setdefault('SQLALCHEMY_DATABASE_URI', db_uri)
    app.config.setdefault('SQLALCHEMY_ECHO', echo)
    app.jinja_env.undefined = StrictUndefined
    db.init_app(app)

    for filter_name in filters.__all__:
        app.jinja_env.filters[filter_name] = getattr(filters, filter_name)

    @app.before_first_request
    def setup():
        db_setup(app, datadir)

    for url, func in routes.items():
        app.route(url)(func)

    return app
