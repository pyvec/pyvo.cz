import datetime
import subprocess
import time

from sqlalchemy import func, and_, or_, desc
from sqlalchemy.orm import joinedload, subqueryload
from sqlalchemy.orm.exc import NoResultFound
from flask import request, Response, url_for
from flask import render_template, jsonify
from flask import current_app as app
from werkzeug.exceptions import abort
from jinja2.exceptions import TemplateNotFound
import ics

from pyvodb import tables
from pyvodb.calendar import get_calendar

from . import filters
from .db import db, db_reload

RELOAD_HOOK_TIME = 0

routes = {}

def route(url, methods=['GET'], translate=True):
    def decorator(func):
        assert url.startswith('/')
        if translate:
            routes[url] = func, {'defaults': {'lang_code': 'cs'},
                                 'methods': methods}
            routes['/en' + url] = func, {'defaults': {'lang_code': 'en'},
                                         'methods': methods}
        else:
            routes[url] = func, {}
        return func
    return decorator


@route('/')
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
    query = query.filter(or_(
        tables.TalkLink.url.startswith('http://www.youtube.com'),
        tables.TalkLink.url.startswith('https://www.youtube.com'),
    ))
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
        if link.youtube_id:
            videos.append(link)

    calendar = get_calendar(db.session, first_year=today.year,
                            first_month=today.month - 1, num_months=3)

    return render_template('index.html', latest_events=latest_events,
                           today=today, videos=videos, calendar=calendar)

@route('/<cityslug>')
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
    try:
        city = query.one()
    except NoResultFound:
        abort(404)

    args = dict(city=city, today=today)
    try:
        return render_template('cities/{}.html'.format(cityslug), **args)
    except TemplateNotFound:
        return render_template('city.html', **args)


@route('/code-of-conduct')
def coc():
    abort(404)  # XXX


@route('/api/venues/<venueslug>/geo', translate=False)
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


@route('/api/pyvo.ics')
def api_ics():
    query = db.session.query(tables.Event)
    query = query.options(joinedload(tables.Event.city))
    query = query.options(joinedload(tables.Event.venue))
    calendar = ics.Calendar()
    for event in query:
        location = '{}, {}, {}'.format(
            event.venue.name,
            event.venue.short_address,
            event.city.name,
        )
        cal_event = ics.Event(
            name=event.title,
            location=location,
            begin=event.start,
            uid='{}-{}@pyvo.cz'.format(event.city.slug, event.date),
        )
        cal_event.geo = '{}:{}'.format(event.venue.latitude,
                                       event.venue.longitude)
        calendar.events.append(cal_event)
    return Response(str(calendar), mimetype='text/calendar')


def make_feed(query, url):
    query = query.options(joinedload(tables.Event.city))
    query = query.options(joinedload(tables.Event.venue))
    query = query.order_by(desc(tables.Event.date))
    from feedgen.feed import FeedGenerator
    fg = FeedGenerator()
    fg.id('http://pyvo.cz')
    fg.title('Pyvo')
    fg.logo('http://ex.com/logo.jpg')
    fg.link(href=url, rel='self')
    fg.subtitle('Srazy Pyvo.cz')
    for event in query:
        fe = fg.add_entry()
        url = url_for('city', cityslug=event.city.slug, _external=True) + '#{}'.format(event.date)
        fe.id(url)
        fe.link(href=url, rel='alternate')
        fe.title(event.title)
        fe.summary(event.description)
        fe.published(event.start)
        fe.updated(event.start)
        # XXX: Put talks into fe.dscription(), videos in link(..., rel='related')
    return fg


@route('/api/pyvo.rss')
def api_rss():
    query = db.session.query(tables.Event)
    feed = make_feed(query, request.url)
    return Response(feed.rss_str(pretty=True), mimetype='application/rss+xml')


@route('/api/pyvo.atom')
def api_atom():
    query = db.session.query(tables.Event)
    feed = make_feed(query, request.url)
    return Response(feed.atom_str(pretty=True), mimetype='application/atom+xml')

@route('/api/reload_hook', methods=['POST'])
def reload_hook():
    # Some really lame password protection (against DoS)
    if app.config['PYVO_PULL_PASSWORD'] is None:
        abort(404, "pull hook not configured")
    try:
        if request.args['password'] != app.config['PYVO_PULL_PASSWORD']:
            abort(500, "bad password")
    except (TypeError, KeyError):
        abort(500, "missing password")

    datadir = app.config['PYVO_DATADIR']

    output = subprocess.check_output(['git', 'pull'], cwd=datadir)
    app.logger.info('Git output: %s', str(output))
    db_reload(datadir)

    output = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=datadir)
    head_commit = output.decode('ascii').strip()
    return jsonify({'result': 'OK', 'HEAD': head_commit})
