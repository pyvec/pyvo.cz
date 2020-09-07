import datetime
import subprocess
import json
import re
from bisect import bisect

from io import BytesIO

import ics
import qrcode

from dateutil.relativedelta import relativedelta
from flask import request, Response, url_for, redirect, g, abort
from flask import render_template, jsonify
from flask import current_app as app
from cachelib import SimpleCache

from . import filters
from .calendar import get_calendar
from .data import load_data
from .event_add import event_add_link


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
    db = app.db
    now = datetime.datetime.now(tz=db.default_timezone)
    today = now.date()

    # Series with latest events
    # Split series into "featured" (recent) and "past" which last took
    # place 6+ months ago.

    featured_events = []
    past_events = []
    for series in db.series.values():
        keys = [event.date for event in series.events]
        best_event_index = bisect(keys, today)
        if best_event_index >= len(keys):
            last_event = series.events[-1]
            if (today - last_event.date).days > 31*6:
                past_events.append(last_event)
            else:
                featured_events.append(last_event)
        else:
            featured_events.append(series.events[best_event_index])

    # order to show meetups in: upcoming first, then by distance from today
    featured_events.sort(key=lambda e: (e.date < today, today - e.date))
    past_events.sort(key=lambda e: e.date, reverse=True)

    videos = get_videos(db.events)

    calendar = get_calendar(
        db, first_year=today.year, first_month=today.month - 1, num_months=3,
    )

    return render_template('index.html', featured_events=featured_events,
                           past_events=past_events,
                           today=today, videos=videos, calendar=calendar)


def get_videos(events, max_len=12):
    """Get `max_len` latest videos"""
    videos = []
    for event in reversed(events):
        for talk in event.talks:
            for link in talk.links:
                if link.kind == 'video':
                    videos.append(link)
                    if len(videos) >= max_len:
                        return videos
    return videos


def min_max_years(events):
    return events[0].date.year, events[-1].date.year


@route('/calendar/', defaults={'year': None})
@route('/calendar/<int:year>/')
def calendar(year=None):
    db = app.db
    today = datetime.date.today()
    if year is None:
        year = today.year
    try:
        start = datetime.datetime(year, 1, 1)
    except ValueError:
        abort(404)

    calendar = get_calendar(
        db, first_year=start.year, first_month=start.month,
        series_slugs=db.series.keys(), num_months=12,
    )

    first_year, last_year = min_max_years(db.events)

    return render_template(
        'calendar.html', today=today, calendar=calendar, year=year,
        first_year=first_year, last_year=last_year,
    )


@route('/<series_slug>/')
@route('/<series_slug>/<int:year>/')
@route('/<series_slug>/<any(all):all>/')
def series(series_slug, year=None, all=None):
    db = app.db

    if series_slug in BACKCOMPAT_SERIES_ALIASES:
        url = url_for('series',
                      series_slug=BACKCOMPAT_SERIES_ALIASES[series_slug])
        return redirect(url)

    today = datetime.date.today()

    series = db.series.get(series_slug)
    if not series:
        abort(404)

    # List of years to show in the pagination
    # If there are no years with events, put the current year there at least
    all_years = sorted(set(event.date.year for event in series.events))
    if all_years:
        first_year = min(all_years)
        last_year = max(all_years)
    else:
        first_year = last_year = today.year

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

    events = list(reversed(series.events))

    if not all:
        if year is None:
            # The 'New' page displays the current year as well as the last one
            events = [e for e in events if e.date.year >= today.year - 1]
        else:
            events = [e for e in events if e.date.year == year]

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

    has_events = bool(events)

    # Split events between future and past
    # (today's event, if any, is considered future)
    past_events = [e for e in events if e.date < today]
    future_events = [e for e in events if e.date >= today]

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

    return render_template(
        'series.html', series=series, today=today,
        year=year, future_events=future_events,
        past_events=past_events,
        featured_event=featured_event,
        organizer_info=series.organizers, all=all,
        first_year=first_year, last_year=last_year,
        all_years=all_years, paginate_prev=paginate_prev,
        paginate_next=paginate_next, has_events=has_events,
        event_add_link=event_add_link,
    )


@route('/<series_slug>/<date_slug>/')
def event(series_slug, date_slug):
    db = app.db
    if series_slug in BACKCOMPAT_SERIES_ALIASES:
        url = url_for('event',
                      series_slug=BACKCOMPAT_SERIES_ALIASES[series_slug],
                      date_slug=date_slug)
        return redirect(url)

    today = datetime.date.today()

    series = db.series.get(series_slug)
    if not series:
        abort(404)

    match = re.match(r'^(\d{4})-(\d{1,2})$', date_slug)
    if not match:
        try:
            number = int(date_slug)
        except ValueError:
            abort(404)
        events = [e for e in series.events if e.number == number]
    else:
        year = int(match.group(1))
        month = int(match.group(2))
        events = [
            e for e in series.events
            if e.date.year == year and e.date.month == month
        ]

    if len(events) != 1:
        abort(404)
    [event] = events

    proper_date_slug = '{0.year:4}-{0.month:02}'.format(event.date)
    if date_slug != proper_date_slug:
        return redirect(url_for('event', series_slug=series_slug,
                                date_slug=proper_date_slug))

    github_link = ("https://github.com/pyvec/pyvo-data/blob/master/./"
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
    db = app.db
    venue = db.venues.get(venueslug)
    if not venue:
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


def make_ics(events, url, *, recurrence_series=()):
    today = datetime.date.today()

    events = []
    last_series_date = {}

    for event in events:
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
            url=url_for(
                'event', series_slug=event.series.slug,
                date_slug=event.slug,
                _external=True,
            ),
            description=event.description,
        )
        cal_event.geo = float(geo_obj.latitude), float(geo_obj.longitude)
        events.append(cal_event)

        if (event.series in last_series_date and
                last_series_date[event.series.slug] < event.date):
            last_series_date[event.series.slug] = event.date

    # XXX: We should use the Series recurrence rule directly,
    # but ics doesn't allow that yet:
    # https://github.com/C4ptainCrunch/ics.py/issues/14
    # Just show the events for the next 6 months (with the limit at a month
    # boundary).
    occurence_limit = (today + relativedelta(months=+6)).replace(day=1)

    for series in recurrence_series:
        since = last_series_date.get(series.slug, today)
        since += datetime.timedelta(days=1)

        if g.lang_code == 'cs':
            name_template = '({} – nepotvrzeno; tradiční termín srazu)'
        else:
            name_template = '({} – tentative date)'
        for occurence in series.next_occurrences(since=since):
            if occurence.date() > occurence_limit:
                break
            cal_event = ics.Event(
                name=name_template.format(series.name),
                begin=occurence,
                uid='{}-{}@pyvo.cz'.format(series.slug, occurence.date()),
                categories=['tentative-date'],
            )
            events.append(cal_event)

    return ics.Calendar(events=events)


def make_feed(events, url):
    from feedgen.feed import FeedGenerator
    fg = FeedGenerator()
    fg.id('http://pyvo.cz')
    fg.title('Pyvo')
    fg.logo(url_for('static', filename='images/krygl.png', _external=True))
    fg.link(href=url, rel='self')
    fg.subtitle('Srazy Pyvo.cz')
    for event in events:
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


def feed_response(events, feed_type, *, recurrence_series=()):
    MIMETYPES = {
        'rss': 'application/rss+xml',
        'atom': 'application/atom+xml',
        'ics': 'text/calendar',
    }
    FEED_MAKERS = {
        'rss': lambda: make_feed(events, request.url).rss_str(pretty=True),
        'atom': lambda: make_feed(events, request.url).atom_str(pretty=True),
        'ics': lambda: str(make_ics(
            events, request.url, recurrence_series=recurrence_series),
        ),
    }

    try:
        mimetype = MIMETYPES[feed_type]
        maker = FEED_MAKERS[feed_type]
    except KeyError:
        abort(404)

    return Response(maker(), mimetype=mimetype)


@route('/api/pyvo.<feed_type>')
def api_feed(feed_type):
    db = app.db
    return feed_response(
        db.events, feed_type, recurrence_series=db.series.values(),
    )


@route('/api/series/<series_slug>.<feed_type>')
def api_series_feed(series_slug, feed_type):
    db = app.db
    series = db.series.get(series_slug)
    if not series:
        abort(4040)

    return feed_response(series.events, feed_type, recurrence_series=[series])


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

    app.db = load_data(datadir)

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

@route('/nepyvo/')
@route('/nepyvo/<path:_any_path>')
def nepyvo_redirect(_any_path=None):
    # Nepyvo meetups are now organized on Facebook. Redirect old URLs.
    return redirect('https://www.facebook.com/groups/894454654024779/')
