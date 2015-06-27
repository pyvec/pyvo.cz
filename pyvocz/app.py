import os
import datetime
import re

from sqlalchemy import func, and_, desc
from sqlalchemy.orm import joinedload, joinedload_all, subqueryload
from sqlalchemy.orm.exc import NoResultFound
from flask import Flask, request
from flask import render_template, jsonify
from flask.ext.sqlalchemy import SQLAlchemy
from werkzeug.exceptions import abort
from jinja2 import evalcontextfilter, escape, StrictUndefined
from jinja2.exceptions import TemplateNotFound
from czech_holidays import Holidays

from pyvodb.load import get_db
from pyvodb import tables

from . import filters

app = Flask(__name__)
app.config.setdefault('SQLALCHEMY_DATABASE_URI', os.environ['SQLALCHEMY_DATABASE_URI'])
app.config.setdefault('SQLALCHEMY_ECHO', True)
app.jinja_env.undefined = StrictUndefined
db = SQLAlchemy(app)

for filter_name in filters.__all__:
    app.jinja_env.filters[filter_name] = getattr(filters, filter_name)


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

    # Latest talk query

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

    # Video query

    query = db.session.query(tables.TalkLink)
    query = query.filter(tables.TalkLink.url.startswith('http://www.youtube.com'))
    query = query.join(tables.TalkLink.talk)
    query = query.join(tables.Talk.event)
    query = query.options(joinedload(tables.TalkLink.talk))
    query = query.options(joinedload(tables.TalkLink.talk, 'event'))
    query = query.options(joinedload(tables.TalkLink.talk, 'event', 'city'))
    query = query.options(subqueryload(tables.TalkLink.talk, 'talk_speakers'))
    query = query.options(joinedload(tables.TalkLink.talk, 'talk_speakers', 'speaker'))
    query = query.order_by(desc(tables.Event.date), tables.Talk.index)
    videos = []
    for link in query[:12]:
        prefix = 'http://www.youtube.com/watch?v='
        match = re.match(re.escape(prefix) + '([-1-9a-zA-Z_]+)', link.url)
        if match:
            videos.append((link, match.group(1)))

    # Calendar

    month_start = today.replace(day=1)
    last_month_start = month_start.replace(month=month_start.month - 1)
    next_month_end = last_month_start.replace(month=month_start.month + 2)
    query = db.session.query(tables.Event)
    query = query.filter(tables.Event.date >= last_month_start)
    query = query.filter(tables.Event.date < next_month_end)
    events_by_date = {e.date: e for e in query}
    week = []
    month = [week]
    months = []
    current = last_month_start
    prev_month = None
    holiday_dict = {}
    while current < next_month_end:
        if current.year not in holiday_dict:
            holiday_dict[current.year] = Holidays(current.year)
        if current.month != prev_month:
            while len(week) < 7:
                week.append((None, None))
            week = [(None, None)] * current.weekday()
            month = [week]
            months.append(month)
            prev_month = current.month
        if week and current.weekday() == 0:
            week = []
            month.append(week)
        week.append((current, events_by_date.get(current)))
        current += datetime.timedelta(days=1)
    max_weeks = max(len(m) for m in months)
    for month in months:
        if month[0][3][0] is not None and len(month) < max_weeks:
            month.insert(0, [(None, None)] * 7)
        if len(month) < max_weeks:
            month.append([(None, None)] * 7)
        for week in month:
            while len(week) < 7:
                week.append((None, None))
    holidays = set()
    for days in holiday_dict.values():
        for day in days:
            holidays.add(day + datetime.timedelta())
    print(holidays)
    print(datetime.date(2015, 5, 1) in holidays)

    return render_template('index.html', latest_events=latest_events,
                           today=today, videos=videos, calendars=months,
                           holidays=holidays)

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


@app.route('/api/venues/<venueslug>/geo')
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
                    "address": filters.nl2br(venue.address),
                },
                "geometry": {
                    "type": "Point",
                    "coordinates": [str(venue.longitude), str(venue.latitude)]
                }
            },
        ]
    })
