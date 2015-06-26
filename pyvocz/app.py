import os
import datetime
import re

from sqlalchemy import func, and_
from sqlalchemy.orm import joinedload, joinedload_all, subqueryload
from sqlalchemy.orm.exc import NoResultFound
from flask import Flask
from flask import render_template, jsonify
from flask.ext.sqlalchemy import SQLAlchemy
from werkzeug.exceptions import abort
from jinja2 import evalcontextfilter, escape, StrictUndefined
from jinja2.exceptions import TemplateNotFound
from markupsafe import Markup

from pyvodb.load import get_db
from pyvodb import tables

app = Flask(__name__)
app.config.setdefault('SQLALCHEMY_DATABASE_URI', os.environ['SQLALCHEMY_DATABASE_URI'])
app.config.setdefault('SQLALCHEMY_ECHO', True)
app.jinja_env.undefined = StrictUndefined
db = SQLAlchemy(app)

@app.template_filter()
def mail_link(address):
    address = address.replace('a', '&#97;')
    address = address.replace('c', '&#99;')
    address = address.replace('.', '&#46;')
    a = address.replace('@', '&#64;')
    b = address.replace('@', '&#64;<!--==≡≡==-->')
    return Markup('<a href="m&#97;ilto://{}">{}</a>'.format(a, b))

_paragraph_re = re.compile(r'(?:\r\n|\r|\n){2,}')
@app.template_filter()
def nl2br(value):
    result = u'\n\n'.join(u'<p>%s</p>' % p.replace('\n', '<br>\n') \
        for p in _paragraph_re.split(escape(value)))
    result = Markup(result)
    return result

@app.before_first_request
def setup():
    # Workaround for https://github.com/mitsuhiko/flask-sqlalchemy/pull/250
    datadir = app.config.get('PYVOCZ_DATA_PATH',
                             os.path.join(app.root_path, 'data'))
    tables.metadata.create_all(db.engine)
    if db.session.query(tables.Event).count():
        print('Skipping DB reload')
        return
    print('Loading database from {}'.format(datadir))
    get_db(datadir, engine=db.engine)
    print('Database loaded')

@app.route('/')
def index():
    today = datetime.date.today()

    subquery = db.session.query(
        tables.Event.city_id,
        func.max(tables.Event.date).label('latest_date'),
    )
    subquery = subquery.group_by(tables.Event.city_id)
    subquery = subquery.subquery()

    query = db.session.query(tables.Event)
    query = query.join(subquery,
                       and_(subquery.c.latest_date == tables.Event.date,
                            subquery.c.city_id == tables.Event.city_id,
                            ))
    # order: upcoming first, then by distance from today
    jd = func.julianday
    query = query.order_by(jd(subquery.c.latest_date) < jd(today),
                           func.abs(jd(subquery.c.latest_date) - jd(today)))
    query = query.options(joinedload(tables.Event.city))
    query = query.options(joinedload(tables.Event.venue))
    latest_events = query.all()

    return render_template('index.html', latest_events=latest_events, today=today)

@app.route('/<cityslug>')
def city(cityslug):
    today = datetime.date.today()

    query = db.session.query(tables.City)
    query = query.filter(tables.City.slug == cityslug)
    query = query.options(joinedload(tables.City.events, 'talks'))
    query = query.options(joinedload(tables.City.events))
    query = query.options(joinedload(tables.City.events, 'venue'))
    query = query.options(joinedload(tables.City.events, 'talks', 'talk_speakers'))
    query = query.options(subqueryload(tables.City.events, 'talks', 'talk_speakers', 'speaker'))
    query = query.options(subqueryload(tables.City.events, 'talks', 'links'))
    city = query.one()

    args = dict(city=city, today=today)
    try:
        return render_template('cities/{}.html'.format(cityslug), **args)
    except TemplateNotFound:
        return render_template('city.html', **args)


@app.route('/code-of-conduct')
def coc():
    abort(404)  # XXX


@app.route('/api/venue/<venueslug>/geo')
def api_venue_geojson(venueslug):
    query = db.session.query(tables.Venue)
    query = query.filter(tables.Venue.slug == venueslug)
    try:
        venue = query.one()
    except NoResultFound:
        abort(404)

    return jsonify({
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {
                    "name": venue.name,
                    "address": nl2br(venue.address),
                },
                "geometry": {
                    "type": "Point",
                    "coordinates": [str(venue.longitude), str(venue.latitude)]
                }
            },
        ]
    })
