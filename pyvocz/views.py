import datetime
import subprocess
import json
import re

from io import BytesIO

import ics
import qrcode

from sqlalchemy import func, or_, desc, extract
from sqlalchemy.orm import joinedload, subqueryload, contains_eager
from sqlalchemy.orm.exc import NoResultFound, MultipleResultsFound
from flask import request, Response, url_for, redirect, g
from flask import render_template, jsonify
from flask import current_app as app
from werkzeug.exceptions import abort
from werkzeug.contrib.cache import SimpleCache

from pyvodb import tables
from pyvodb.calendar import get_calendar

from . import filters
from .db import db, db_reload


FEATURED_SERIES = (
    'brno-pyvo',
    'praha-pyvo',
    'ostrava-pyvo',
    'olomouc-pyvo',
    'plzen-pyvo',
    'liberec-pyvo',
    'hradec-pyvo',
)

BACKCOMPAT_SERIES_ALIASES = {
    'brno': 'brno-pyvo',
    'praha': 'praha-pyvo',
    'ostrava': 'ostrava-pyvo',
    'olomouc': 'olomouc-pyvo',
    'plzen': 'plzen-pyvo',
    'liberec': 'liberec-pyvo',
}


# Be careful when using SimpleCache!
# See: http://werkzeug.pocoo.org/docs/contrib/cache/
#      #werkzeug.contrib.cache.SimpleCache
cache = SimpleCache(threshold=500, default_timeout=300)

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

    # order to show meetups in: upcoming first, then by distance from today
    _jd = func.julianday
    order_args = (_jd(tables.Event.date) < _jd(today),
                  func.abs(_jd(tables.Event.date) - _jd(today)))

    # Make a subquery to select the best event from a series
    # (according to the order above)
    subquery = db.session.query(tables.Event.date)
    subquery = subquery.filter(tables.Event.series_slug == tables.Series.slug)
    subquery = subquery.order_by(*order_args)
    subquery = subquery.limit(1).correlate(tables.Series)
    subquery = subquery.subquery()

    # Select all featured series, along with their best event
    query = db.session.query(tables.Event)
    query = query.join(tables.Series, tables.Event.date == subquery)
    query = query.filter(tables.Event.series_slug.in_(FEATURED_SERIES))
    query = query.order_by(*order_args)
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
    query = query.filter(tables.TalkLink.kind == 'video')
    query = query.options(joinedload(tables.TalkLink.talk))
    query = query.options(joinedload(tables.TalkLink.talk, 'event'))
    query = query.options(joinedload(tables.TalkLink.talk, 'event', 'series'))
    query = query.options(subqueryload(tables.TalkLink.talk, 'talk_speakers'))
    query = query.options(joinedload(tables.TalkLink.talk, 'talk_speakers',
                                     'speaker'))
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


def years_with_events(series_slug):
    query = db.session.query(tables.Event)
    query = query.filter(tables.Event.series_slug == series_slug)
    year_col = func.extract('year', tables.Event.date)
    query = query.with_entities(year_col)
    query = query.order_by(year_col)
    return [x[0] for x in query.distinct()]


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

    # List of years to show in the pagination
    # If there are no years with events, put the current year there at least
    all_years = years_with_events(series_slug) or [today.year]
    first_year, last_year = min(all_years), max(all_years)

    if last_year == today.year and len(all_years) > 1:
        # The current year is displayed on the 'New' page (year=None)
        all_years.remove(last_year)
        last_year = max(all_years)

    if year is not None:
        if year > last_year:
            # Instead of showing a future year, redirect to the 'New' page
            return redirect(url_for('series', series_slug=series_slug))
        if year not in all_years:
            # Otherwise, if there are no events in requested year, return 404.
            abort(404)

    if all is not None:
        paginate_prev = {'year': first_year}
        paginate_next = {'all': 'all'}
    elif year is None:
        paginate_prev = {'year': None}
        paginate_next = {'year': last_year}
    else:
        past_years = [y for y in all_years if y < year]
        if past_years:
            paginate_next = {'year': max(past_years)}
        else:
            paginate_next = {'all': 'all'}

        future_years = [y for y in all_years if y > year]
        if future_years:
            paginate_prev = {'year': min(future_years)}
        else:
            paginate_prev = {'year': None}

    query = db.session.query(tables.Series)
    query = query.filter(tables.Series.slug == series_slug)
    query = query.join(tables.Series.events)
    query = query.options(contains_eager(tables.Series.events))
    query = query.options(joinedload(tables.Series.events, 'talks'))
    query = query.options(joinedload(tables.Series.events, 'venue'))
    query = query.options(joinedload(tables.Series.events, 'talks',
                                     'talk_speakers'))
    query = query.options(subqueryload(tables.Series.events, 'talks',
                                       'talk_speakers', 'speaker'))
    query = query.options(subqueryload(tables.Series.events, 'talks', 'links'))
    query = query.order_by(tables.Event.date.desc())

    if not all:
        if year is None:
            # The 'New' page displays the current year as well as the last one
            query = query.filter(tables.Event.date >=
                                 datetime.date(today.year - 1, 1, 1))
        else:
            query = query.filter(tables.Event.date >=
                                 datetime.date(year, 1, 1))
            query = query.filter(tables.Event.date <
                                 datetime.date(year + 1, 1, 1))

    try:
        series = query.one()
        has_events = True
    except NoResultFound:
        has_events = False

        # The series has no events during the selected timeframe so at least
        # load general information on the series so we can properly display
        # the heading.
        query = db.session.query(tables.Series)
        query = query.filter(tables.Series.slug == series_slug)
        try:
            series = query.one()
        except NoResultFound:
            abort(404)

    # Split events between future and past
    # (today's event, if any, is considered future)
    past_events = [e for e in series.events if e.date < today]
    future_events = [e for e in series.events if e.date >= today]

    # Events are ordered closest first;
    #  for future ones this means ascending order
    future_events.reverse()

    featured_event = None
    if year is None:
        # Pop the featured event -- closest future one, or latest past one
        if future_events:
            featured_event = future_events.pop(0)
        elif past_events:
            featured_event = past_events.pop(0)

    organizer_info = json.loads(series.organizer_info)
    return render_template('series.html', series=series, today=today,
                           year=year, future_events=future_events,
                           past_events=past_events,
                           featured_event=featured_event,
                           organizer_info=organizer_info, all=all,
                           first_year=first_year, last_year=last_year,
                           all_years=all_years, paginate_prev=paginate_prev,
                           paginate_next=paginate_next, has_events=has_events)


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
    query = query.options(subqueryload(tables.Event.links))
    query = query.options(subqueryload(tables.Event.talks, 'talk_speakers',
                                       'speaker'))
    query = query.options(subqueryload(tables.Event.talks, 'links'))

    try:
        event = query.one()
    except (NoResultFound, MultipleResultsFound):
        abort(404)

    proper_date_slug = '{0.year:4}-{0.month:02}'.format(event.date)
    if date_slug != proper_date_slug:
        return redirect(url_for('event', series_slug=series_slug,
                                date_slug=proper_date_slug))

    github_link = ("https://github.com/pyvec/pyvo-data/blob/master/"
                   "{filepath}".format(filepath=event._source))

    return render_template('event.html', event=event, today=today,
                           github_link=github_link)


@route('/<series_slug>/<date_slug>/qrcode.png')
def event_qrcode(series_slug, date_slug):
    url = url_for('event', _external=True,
                  series_slug=series_slug, date_slug=date_slug)

    qr_byte_io = cache.get(url)
    if qr_byte_io is None:
        qr_img = qrcode.make(url,
                             box_size=5,
                             border=0)
        qr_byte_io = BytesIO()
        qr_img.save(qr_byte_io, 'PNG')
        qr_byte_io.seek(0)
        cache.set(url, qr_byte_io, timeout=5 * 60)

    return Response(qr_byte_io, mimetype='image/png')


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


def make_ics(query, url, *, recurrence_series=()):
    today = datetime.date.today()

    query = query.options(joinedload(tables.Event.city))
    query = query.options(joinedload(tables.Event.venue))

    events = []
    last_series_date = {}

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
        events.append(cal_event)

        if (event.series in last_series_date and
                last_series_date[event.series] < event.date):
            last_series_date[event.series] = event.date

    for series in recurrence_series:
        since = last_series_date.get(series, today)
        since += datetime.timedelta(days=1)

        # XXX: We should use the Series recurrence rule directly,
        # but ics doesn't allow that yet:
        # https://github.com/C4ptainCrunch/ics.py/issues/14
        # Just show the 6 next events.
        if g.lang_code == 'cs':
            name_template = '({} – nepotvrzeno; tradiční termín srazu)'
        else:
            name_template = '({} – tentative date)'
        for occurence in series.next_occurrences(n=6, since=since):
            cal_event = ics.Event(
                name=name_template.format(series.name),
                begin=occurence,
                uid='{}-{}@pyvo.cz'.format(series.slug, occurence.date()),
            )
            events.append(cal_event)

    return ics.Calendar(events=events)


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
        # XXX: Put talks into fe.dscription(),
        # videos in link(..., rel='related')
    return fg


def feed_response(query, feed_type, *, recurrence_series=()):
    MIMETYPES = {
        'rss': 'application/rss+xml',
        'atom': 'application/atom+xml',
        'ics': 'text/calendar',
    }
    FEED_MAKERS = {
        'rss': lambda: make_feed(query, request.url).rss_str(pretty=True),
        'atom': lambda: make_feed(query, request.url).atom_str(pretty=True),
        'ics': lambda: str(make_ics(query, request.url,
                                    recurrence_series=recurrence_series)),
    }

    try:
        mimetype = MIMETYPES[feed_type]
        maker = FEED_MAKERS[feed_type]
    except KeyError:
        abort(404)

    return Response(maker(), mimetype=mimetype)


@route('/api/pyvo.<feed_type>')
def api_feed(feed_type):
    query = db.session.query(tables.Series)
    query = query.filter(tables.Series.slug.in_(FEATURED_SERIES))
    series = query.all()

    query = db.session.query(tables.Event)
    query = query.filter(tables.Event.series_slug.in_(FEATURED_SERIES))
    return feed_response(query, feed_type, recurrence_series=series)


@route('/api/series/<series_slug>.<feed_type>')
def api_series_feed(series_slug, feed_type):
    series = db.session.query(tables.Series).get(series_slug)

    query = db.session.query(tables.Event)
    query = query.filter(tables.Event.series == series)
    return feed_response(query, feed_type, recurrence_series=[series])


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
        return jsonify({'result': 'OK', 'HEAD': head_commit,
                        'note': 'unchanged'})

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


@route('/personal-info/')
def personal_info():
    return render_template('personal-info.html')


@route('/googleb01eac5297e2560c.html')
def google_verification():
    # Verifies pyvo.cz's claim to its YouTube channel:
    #  https://www.youtube.com/channel/UCaT4I7hjX9iH1YFvNvuu84A
    # Should not be removed.
    return 'google-site-verification: googleb01eac5297e2560c.html'
