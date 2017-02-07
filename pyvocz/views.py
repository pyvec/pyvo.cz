import datetime
import subprocess
import json
import time
import re

from sqlalchemy import func, and_, or_, desc, extract
from sqlalchemy.orm import joinedload, subqueryload, contains_eager
from sqlalchemy.orm.exc import NoResultFound, MultipleResultsFound
from flask import request, Response, url_for, redirect
from flask import render_template, jsonify
from flask import current_app as app
from werkzeug.exceptions import abort
from werkzeug.routing import Rule
from jinja2.exceptions import TemplateNotFound
import ics

from pyvodb import tables
from pyvodb.calendar import get_calendar

from . import filters
from .db import db, db_reload


FEATURED_SERIES = 'brno-pyvo', 'praha-pyvo', 'ostrava-pyvo'

BACKCOMPAT_SERIES_ALIASES = {
    'brno': 'brno-pyvo',
    'praha': 'praha-pyvo',
    'ostrava': 'ostrava-pyvo',
}

routes = []

def route(url, methods=['GET'], translate=True, **kwargs):
    def decorator(func):
        assert url.startswith('/')
        options = dict(kwargs, methods=methods)
        if translate:
            routes.append((
                url, func,
                dict(options, defaults={'lang_code': 'cs'}),
            ))
            routes.append((
                '/en' + url, func,
                dict(options, defaults={'lang_code': 'en'}),
            ))
        else:
            routes.append((url, func, options))
        return func
    return decorator


@route('/')
def index():
    today = datetime.date.today()

    # Latest talk query

    subquery = db.session.query(
        tables.Event.series_slug,
        func.max(tables.Event.date).label('latest_date'),
    )
    subquery = subquery.group_by(tables.Event.series_slug)
    subquery = subquery.subquery()

    query = db.session.query(tables.Event)
    query = query.join(subquery,
                       and_(subquery.c.latest_date == tables.Event.date,
                            subquery.c.series_slug == tables.Event.series_slug,
                            ))
    query = query.filter(tables.Event.series_slug.in_(FEATURED_SERIES))
    # order: upcoming first, then by distance from today
    jd = func.julianday
    query = query.order_by(jd(subquery.c.latest_date) < jd(today),
                           func.abs(jd(subquery.c.latest_date) - jd(today)))
    query = query.options(joinedload(tables.Event.series))
    query = query.options(joinedload(tables.Event.venue))
    featured_events = query.all()

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
    query = query.options(joinedload(tables.TalkLink.talk, 'event', 'series'))
    query = query.options(subqueryload(tables.TalkLink.talk, 'talk_speakers'))
    query = query.options(joinedload(tables.TalkLink.talk, 'talk_speakers', 'speaker'))
    query = query.order_by(desc(tables.Event.date), tables.Talk.index)
    videos = []
    for link in query[:12]:
        if link.youtube_id:
            videos.append(link)

    calendar = get_calendar(db.session, first_year=today.year,
                            series_slugs=FEATURED_SERIES,
                            first_month=today.month - 1, num_months=3)

    return render_template('index.html', featured_events=featured_events,
                           today=today, videos=videos, calendar=calendar)


def min_max_years(query):
    year_col = func.extract('year', tables.Event.date)
    query = query.with_entities(func.min(year_col), func.max(year_col))
    first_year, last_year = query.one()
    return first_year, last_year


@route('/calendar/', defaults={'year': None})
@route('/calendar/<int:year>/')
def calendar(year=None):
    today = datetime.date.today()
    if year is None:
        year = today.year
    try:
        start = datetime.datetime(year, 1, 1)
    except ValueError:
        abort(404)

    calendar = get_calendar(db.session, first_year=start.year,
                            series_slugs=FEATURED_SERIES,
                            first_month=start.month, num_months=12)

    first_year, last_year = min_max_years(db.session.query(tables.Event))

    return render_template('calendar.html', today=today, calendar=calendar,
                           year=year,
                           first_year=first_year, last_year=last_year)


@route('/<series_slug>/')
@route('/<series_slug>/<int:year>/')
@route('/<series_slug>/<any(all):all>/')
def series(series_slug, year=None, all=None):
    if series_slug in BACKCOMPAT_SERIES_ALIASES:
        url = url_for('series',
                      series_slug=BACKCOMPAT_SERIES_ALIASES[series_slug])
        return redirect(url)

    today = datetime.date.today()

    first_year, last_year = min_max_years(db.session.query(tables.Event))
    if last_year == today.year:
        # The current year is displayed on the 'New' page (year=None)
        last_year -= 1

    if year is not None:
        if year > last_year:
            year = None
        if year < first_year:
            year = first_year

    if all is not None:
        paginate_prev = {'year': first_year}
        paginate_next = {'all': 'all'}
    elif year is None:
        paginate_prev = {'year': None}
        paginate_next = {'year': last_year}
    elif year >= last_year:
        paginate_prev = {'year': None}
        paginate_next = {'year': year - 1}
    elif year <= first_year:
        paginate_prev = {'year': year + 1}
        paginate_next = {'all': 'all'}
    else:
        paginate_prev = {'year': year + 1}
        paginate_next = {'year': year - 1}

    query = db.session.query(tables.Series)
    query = query.filter(tables.Series.slug == series_slug)
    query = query.join(tables.Series.events)
    query = query.options(contains_eager(tables.Series.events))
    query = query.options(joinedload(tables.Series.events, 'talks'))
    query = query.options(joinedload(tables.Series.events, 'venue'))
    query = query.options(joinedload(tables.Series.events, 'talks', 'talk_speakers'))
    query = query.options(subqueryload(tables.Series.events, 'talks', 'talk_speakers', 'speaker'))
    query = query.options(subqueryload(tables.Series.events, 'talks', 'links'))
    query = query.order_by(tables.Event.date.desc())

    if not all:
        if year is None:
            # The 'New' page displays the current year as well as the last one
            query = query.filter(tables.Event.date >= datetime.date(today.year - 1, 1, 1))
        else:
            query = query.filter(tables.Event.date >= datetime.date(year, 1, 1))
            query = query.filter(tables.Event.date < datetime.date(year + 1, 1, 1))

    try:
        series = query.one()
    except NoResultFound:
        abort(404)

    organizer_info = json.loads(series.organizer_info)
    return render_template('series.html', series=series, today=today, year=year,
                           organizer_info=organizer_info, all=all,
                           first_year=first_year, last_year=last_year,
                           paginate_prev=paginate_prev,
                           paginate_next=paginate_next)


@route('/<series_slug>/<date_slug>/')
def event(series_slug, date_slug):
    if series_slug in BACKCOMPAT_SERIES_ALIASES:
        url = url_for('event',
                      series_slug=BACKCOMPAT_SERIES_ALIASES[series_slug],
                      date_slug=date_slug)
        return redirect(url)

    today = datetime.date.today()

    query = db.session.query(tables.Event)
    query = query.join(tables.Series)
    query = query.filter(tables.Series.slug == series_slug)

    match = re.match(r'^(\d{4})-(\d{1,2})$', date_slug)
    if not match:
        try:
            number = int(date_slug)
        except ValueError:
            abort(404)
        query = query.filter(tables.Event.number == number)
    else:
        year = int(match.group(1))
        month = int(match.group(2))
        query = query.filter(extract('year', tables.Event.date) == year)
        query = query.filter(extract('month', tables.Event.date) == month)

    query = query.options(joinedload(tables.Event.talks))
    query = query.options(joinedload(tables.Event.venue))
    query = query.options(joinedload(tables.Event.talks, 'talk_speakers'))
    query = query.options(subqueryload(tables.Event.talks, 'talk_speakers', 'speaker'))
    query = query.options(subqueryload(tables.Event.talks, 'links'))

    try:
        event = query.one()
    except (NoResultFound, MultipleResultsFound):
        abort(404)

    proper_date_slug = '{0.year:4}-{0.month:02}'.format(event.date)
    if date_slug != proper_date_slug:
        return redirect(url_for('event', series_slug=series_slug,
                                date_slug=proper_date_slug))

    return render_template('event.html', event=event, today=today)


@route('/code-of-conduct/')
def coc():
    abort(404)  # XXX


@route('/api/venues/<venueslug>/geo/', translate=False)
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

def make_ics(query, url):
    query = query.options(joinedload(tables.Event.city))
    query = query.options(joinedload(tables.Event.venue))
    calendar = ics.Calendar()
    for event in query:
        if event.venue:
            location = '{}, {}, {}'.format(
                event.venue.name,
                event.venue.short_address,
                event.city.name,
            )
            geo_obj = event.venue
        else:
            location = event.city.name
            geo_obj = event.city
        cal_event = ics.Event(
            name=event.title,
            location=location,
            begin=event.start,
            uid='{}-{}@pyvo.cz'.format(event.series_slug, event.date),
        )
        cal_event.geo = '{}:{}'.format(geo_obj.latitude,
                                       geo_obj.longitude)
        calendar.events.append(cal_event)
    return calendar

def make_feed(query, url):
    query = query.options(joinedload(tables.Event.city))
    query = query.options(joinedload(tables.Event.venue))
    query = query.order_by(desc(tables.Event.date))
    from feedgen.feed import FeedGenerator
    fg = FeedGenerator()
    fg.id('http://pyvo.cz')
    fg.title('Pyvo')
    fg.logo(url_for('static', filename='images/krygl.png', _external=True))
    fg.link(href=url, rel='self')
    fg.subtitle('Srazy Pyvo.cz')
    for event in query:
        fe = fg.add_entry()
        url = filters.event_url(event, _external=True)
        fe.id(url)
        fe.link(href=url, rel='alternate')
        fe.title(event.title)
        fe.summary(event.description)
        fe.published(event.start)
        fe.updated(event.start)
        # XXX: Put talks into fe.dscription(), videos in link(..., rel='related')
    return fg


def feed_response(query, feed_type):
    MIMETYPES = {
        'rss': 'application/rss+xml',
        'atom': 'application/atom+xml',
        'ics': 'text/calendar',
    }
    FEED_MAKERS = {
        'rss': lambda: make_feed(query, request.url).rss_str(pretty=True),
        'atom': lambda: make_feed(query, request.url).atom_str(pretty=True),
        'ics': lambda: str(make_ics(query, request.url)),
    }

    try:
        mimetype = MIMETYPES[feed_type]
        maker = FEED_MAKERS[feed_type]
    except KeyError:
        abort(404)

    return Response(maker(), mimetype=mimetype)


@route('/api/pyvo.<feed_type>')
def api_feed(feed_type):
    query = db.session.query(tables.Event)
    return feed_response(query, feed_type)


@route('/api/series/<series_slug>.<feed_type>')
def api_series_feed(series_slug, feed_type):
    query = db.session.query(tables.Event)
    query = query.filter(tables.Event.series_slug == series_slug)
    return feed_response(query, feed_type)


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

    output = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=datadir)
    old_head_commit = output.decode('ascii').strip()

    output = subprocess.check_output(['git', 'pull'], cwd=datadir)
    app.logger.info('Git output: %s', str(output))

    output = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=datadir)
    head_commit = output.decode('ascii').strip()

    if old_head_commit == head_commit:
        return jsonify({'result': 'OK', 'HEAD': head_commit, 'note': 'unchanged'})

    db_reload(datadir)

    return jsonify({'result': 'OK', 'HEAD': head_commit})

@route('/', subdomain='<subdomain>')
def subdomain_redirect(subdomain):
    ALIASES = {
        'brnenske': 'brno-pyvo',
        'ostravske': 'ostrava-pyvo',
        'prazske': 'praha-pyvo',
        'prague': 'praha-pyvo',
        **BACKCOMPAT_SERIES_ALIASES,
    }
    subdomain = ALIASES.get(subdomain, subdomain)
    return redirect(url_for('series', series_slug=subdomain))

@route('/feedback')
def feedback_form_redirect():
    feedback_form_url = (
        'https://docs.google.com/forms/d/e/'
        '1FAIpQLSdgnx9ljKYuC2FDWhCHDu8uHteN4uozHejbGfw2iEyt97q6fQ/viewform'
    )
    return redirect(feedback_form_url)

@route('/zaloz')
def zaloz_redirect():
    return redirect('https://pyvec-guide.readthedocs.io/guides/meetup.html')
