import os

from flask import Flask, g, url_for, request
from jinja2 import StrictUndefined

from . import filters
from .db import db, db_setup
from .views import routes

DEFAULT_DATA_DIR = os.path.join(os.path.dirname(__file__), 'pyvo-data')

def create_app(db_uri, datadir=DEFAULT_DATA_DIR, echo=True, pull_password=None,
               host=None, port=5000):
    datadir = os.path.abspath(datadir)

    app = Flask(__name__)
    app.config.setdefault('SQLALCHEMY_DATABASE_URI', db_uri)
    app.config.setdefault('SQLALCHEMY_ECHO', echo)
    app.config.setdefault('PYVO_DATADIR', datadir)
    app.config.setdefault('PYVO_PULL_PASSWORD', pull_password)
    if host:
        app.config['SERVER_NAME'] = '{}:{}'.format(host, port)
    app.jinja_env.undefined = StrictUndefined
    db.init_app(app)

    for filter_name in filters.__all__:
        app.jinja_env.filters[filter_name] = getattr(filters, filter_name)

    @app.template_global()
    def url_for_lang(lang_code):
        args = dict(request.view_args)
        args['lang_code'] = lang_code
        return url_for(request.endpoint, **args)

    @app.template_global()
    def tr(cs, en):
        if g.lang_code == 'cs':
            return cs
        elif g.lang_code == 'en':
            return en
        raise ValueError(g.lang_code)

    @app.before_first_request
    def setup():
        db_setup(datadir)

    @app.url_value_preprocessor
    def pull_lang_code(endpoint, values):
        if values:
            g.lang_code = values.pop('lang_code', None)

    @app.url_defaults
    def add_language_code(endpoint, values):
        if 'lang_code' in values or not g.lang_code:
            return
        if app.url_map.is_endpoint_expecting(endpoint, 'lang_code'):
            values['lang_code'] = g.lang_code

    for url, func, options in routes:
        app.route(url, **options)(func)

    return app
