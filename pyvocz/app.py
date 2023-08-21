import os
from urllib.parse import urlparse, urlunparse
import binascii
import datetime

from flask import Flask, g, url_for, redirect, request
from jinja2 import StrictUndefined

from . import filters
from .views import routes
from .data import load_data

DEFAULT_DATA_DIR = os.path.join(os.path.dirname(__file__), 'pyvo-data')


def create_app(datadir=DEFAULT_DATA_DIR, echo=True, pull_password=None,
               host=None, port=5000):
    datadir = os.path.abspath(datadir)

    app = Flask(__name__)
    app.config.setdefault('PYVO_DATADIR', datadir)
    app.config.setdefault('PYVO_PULL_PASSWORD', pull_password)
    app.config.setdefault('PROPAGATE_EXCEPTIONS', True)

    app.db = load_data(datadir)

    if host:
        server_name = host
        if port != 80:
            server_name += ':{}'.format(port)
        app.config['SERVER_NAME'] = server_name
    app.jinja_env.undefined = StrictUndefined
    app.jinja_env.globals['get_today'] = datetime.date.today

    tag = binascii.hexlify(os.urandom(16))
    app.jinja_env.globals['_static_cache_tag'] = tag

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

    @app.before_request
    def redirect_subdomains():
        scheme, netloc, path, params, query, fragment = urlparse(request.url)
        if netloc.startswith('www.'):
            # Remove leading 'www.' from the hostname
            netloc = netloc[4:]
            url = urlunparse((scheme, netloc, path, params, query, fragment))
            return redirect(url)

    for url, func, options in routes:
        app.route(url, **options)(func)

    return app
