import datetime

from sqlalchemy import func, and_, desc
from sqlalchemy.orm import joinedload, subqueryload
from sqlalchemy.orm.exc import NoResultFound
from flask import request, Response, url_for
from flask import render_template, jsonify
from werkzeug.exceptions import abort
from jinja2.exceptions import TemplateNotFound
from czech_holidays import Holidays
import ics

from pyvodb import tables

from . import filters
from .db import db


routes = {}

def route(url):
    def decorator(func):
        routes[url] = func
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
        if link.youtube_id:
            videos.append(link)

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

    return render_template('index.html', latest_events=latest_events,
                           today=today, videos=videos, calendars=months,
                           holidays=holidays)

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
    city = query.one()

    args = dict(city=city, today=today)
    try:
        return render_template('cities/{}.html'.format(cityslug), **args)
    except TemplateNotFound:
        return render_template('city.html', **args)


@route('/code-of-conduct')
def coc():
    abort(404)  # XXX


@route('/api/venues/<venueslug>/geo')
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
