from pathlib import Path
from typing import Dict, List, Optional, Any
import datetime
import re
from urllib.parse import urlparse
import itertools

import attr
from  attr import attrs
import yaml
from dateutil import tz, rrule, relativedelta

from .typecheck import typecheck


CET = tz.gettz('Europe/Prague')
YOUTUBE_RE = re.compile(r'''(?x)https?://
                        (?:
                            (?:www\.youtube\.com/watch\?v=)|
                            (?:youtu\.be/)
                        )
                        ([-0-9a-zA-Z_]+)''')

def load_data(datadir):
    path = Path(datadir)
    with (path / 'meta.yaml').open() as f:
        meta = Meta(**yaml.safe_load(f))
    data = dict_from_path(path, path, exclude=meta.ignored_files)

    return Root.load(data)


def dict_from_path(path, base, *, exclude=()):
    if path.is_file():
        with path.open() as f:
            result = yaml.safe_load(f)
            result['_source'] = path.relative_to(base)
            return result
    else:
        result = {}
        for child in Path(path).iterdir():
            if child.name not in exclude and not child.name.startswith('.'):
                result[child.stem] = dict_from_path(child, base)
        return result

@attrs(auto_attribs=True)
class Meta:
    version: int
    ignored_files: List[Path]


@attrs(auto_attribs=True, slots=True)
class Location:
    latitude: str
    longitude: str


@attrs(auto_attribs=True, slots=True)
class Venue:
    """A venue to old events in"""
    name: str

    # Unique identifier for use in URLs
    slug: str

    # City of the venue
    city: str

    # Address of the venue
    address: Optional[str]

    # Notes about the venue, e.g. directions to get there
    notes: Optional[str]

    location: Location
    home_city: "City" = None

    @classmethod
    def load(cls, data, slug):
        return cls(
            name=data['name'],
            city=data['city'],
            slug=slug,
            address=data.get('address'),
            location=Location(**data['location']),
            notes=data.get('notes'),
        )

    @property
    def short_address(self):
        if self.address is not None:
            return self.address.splitlines()[0]

    @property
    def latitude(self):
        return self.location.latitude

    @property
    def longitude(self):
        return self.location.longitude


@attrs(auto_attribs=True, slots=True)
class City:
    """A city that holds events"""

    # Name of the city
    name: str

    # Unique identifier for use in URLs
    slug: str

    # Venues that take place in (or near) this city
    venues: Dict[str, Venue]

    location: Location

    @classmethod
    def load(cls, data, slug):
        self = cls(
            name=data['city']['name'],
            slug=slug,
            location=Location(**data['city']['location']),
            venues={
                slug: Venue.load(v, slug)
                for slug, v in data.get('venues', {}).items()
            },
        )
        for venue in self.venues.values():
            venue.home_city = self
        return self

@attrs(auto_attribs=True, slots=True)
class TalkLink:
    kind: Optional[str]
    url: str
    talk: "Talk" = None

    @classmethod
    def load(cls, data):
        if len(data) > 1:
            raise ValueError('coverage dict too long')
        for kind, url in data.items():
            return cls(
                kind=kind,
                url=url,
            )

    @property
    def hostname(self):
        return urlparse(self.url).hostname

    @property
    def youtube_id(self):
        match = YOUTUBE_RE.match(self.url)
        if match:
            return match.group(1)


@attrs(auto_attribs=True, slots=True)
class Speaker:
    name: str


@attrs(auto_attribs=True, slots=True)
class Talk:
    title: str
    description: Optional[str]
    links: List[TalkLink]
    speakers: List[Speaker]

    # True if this is a lightning talk
    is_lightning: bool

    event: "Event" = None

    @classmethod
    def load(cls, data):
        self = cls(
            title=data['title'],
            description=data.get('description'),
            speakers=[Speaker(s) for s in data.get('speakers', ())],
            links=
                [TalkLink(None, c) for c in data.get('urls', [])] +
                [TalkLink.load(c) for c in data.get('coverage', [])],
            is_lightning=data.get('lightning', False),
        )
        for link in self.links:
            link.talk = self
        return self

    @property
    def youtube_id(self):
        for link in self.links:
            yid = link.youtube_id
            if yid:
                return yid


@attrs(auto_attribs=True, slots=True)
class EventLink:
    url: str


@attrs(auto_attribs=True, slots=True)
class Event:
    """An event."""

    # General name of the event. Often, this is the same as the series name
    name: str

    # Venue where the event takes place
    venue: Optional[Venue]

    # Serial number of the event (if kept track of)
    number: Optional[int]

    # Topic (or sub-title) of the event
    topic: Optional[str]

    # City where the event takes place
    city: City

    # Description in Markdown format
    description: Optional[str]

    start: datetime.datetime
    talks: List[Talk]
    links: List[EventLink]

    # Path where the data was loaded from (relative to data directory root)
    _source: Optional[Path]

    # The series this event belongs to
    series: "Series" = None

    @classmethod
    def load(cls, data, slug, *, cities, venues):
        venue_ident = data.get('venue')
        if venue_ident:
            venue = venues[data['venue']]
        else:
            venue = None

        start = data['start']
        if not hasattr(start, 'time'):
            start = datetime.datetime.combine(start, datetime.time(hour=19))
        start = start.replace(tzinfo=CET)

        self = cls(
            name=data['name'],
            venue=venue,
            number=data.get('number'),
            topic=data.get('topic'),
            city=cities[data['city']],
            start=start,
            description=data.get('description'),
            talks=[Talk.load(t) for t in data.get('talks', ())],
            links=[EventLink(l) for l in data.get('urls', ())],
            source=data['_source'],
        )
        for talk in self.talks:
            talk.event = self
        return self

    @property
    def title(self):
        parts = [self.name]
        if self.number is not None:
            parts.append('#{}'.format(self.number))
        elif self.topic:
            parts.append('–')
        if self.topic:
            parts.append(self.topic)
        return ' '.join(parts)

    @property
    def slug(self):
        """Identifier for use in URLs. Unique within the series"""
        return self.date.strftime('%Y-%m')

    @property
    def date(self):
        return self.start.date()

    @property
    def start_time(self):
        return self.start.time()


@attrs(auto_attribs=True)
class Organizer:
    name: str
    phone: str = None
    mail: str = None
    web: str = None


@attrs(auto_attribs=True)
class Series:
    """A series of events"""

    # Name of the series, like "Brněnské Pyvo"
    name: str

    # Unique identifier for use in URLs
    slug: str

    # City this series usually takes place at
    home_city: City

    # Descriptions of the entire series
    description_cs: Optional[str]
    description_en: Optional[str]

    events: List[Event]

    # Info about organizers
    organizers: List[dict]
 
    # RFC 2445 recurrence rule for regular event dates
    recurrence_rule: Optional[Any]

    # Basic type of the series' recurrence scheme
    recurrence_scheme: Optional[str]

    # Human-readable description of the recurrence rule
    recurrence_description_cs: Optional[str]
    recurrence_description_en: Optional[str]

    # Path where the data was loaded from (relative to data directory root)
    _source: Optional[Path]

    @classmethod
    def load(cls, data, slug, *, cities, venues):
        recurrence = data['series'].get('recurrence')
        if recurrence:
            rrule_str = recurrence['rrule']
            rrule.rrulestr(rrule_str)  # check rrule syntax
            recurrence_attrs = {
                'recurrence_rule': rrule_str,
                'recurrence_scheme': recurrence['scheme'],
                'recurrence_description_cs': recurrence['description']['cs'],
                'recurrence_description_en': recurrence['description']['en'],
            }
        else:
            recurrence_attrs = {
                'recurrence_rule': None,
                'recurrence_scheme': None,
                'recurrence_description_cs': None,
                'recurrence_description_en': None,
            }

        self = cls(
            events=sorted(
                (
                    Event.load(e, slug, cities=cities, venues=venues)
                    for slug, e in data.get('events', {}).items()
                ),
                key=lambda e: e.start
            ),
            slug=slug,
            name=data['series']['name'],
            home_city=cities[data['series']['city']],
            description_cs=data['series']['description']['cs'],
            description_en=data['series']['description']['en'],
            organizers=[dict(o) for o in data['series']['organizer-info']],
            source=data['series']['_source'],
            **recurrence_attrs,
        )
        for event in self.events:
            event.series = self
        return self

    def next_occurrences(self, n=None, since=None):
        """Yield the next planned occurrences after the date "since"

        The `since` argument can be either a date or datetime onject.
        If not given, it defaults to the date of the last event that's
        already planned.

        If `n` is given, the result is limited to that many dates;
        otherwise, infinite results may be generated.
        Note that less than `n` results may be yielded.
        """
        scheme = self.recurrence_scheme
        if scheme is None:
            return ()

        last_planned_event = self.events[-1]

        if since is None or since < last_planned_event.date:
            since = last_planned_event.date

        start = getattr(since, 'date', since)

        start += relativedelta.relativedelta(days=+1)

        if (scheme == 'monthly'
                and last_planned_event
                and last_planned_event.date.year == start.year
                and last_planned_event.date.month == start.month):
            # Monthly events try to have one event per month, so exclude
            # the current month if there was already a meetup
            start += relativedelta.relativedelta(months=+1)
            start = start.replace(day=1)

        start = datetime.datetime.combine(start, datetime.time(tzinfo=CET))
        result = rrule.rrulestr(self.recurrence_rule, dtstart=start)
        if n is not None:
            result = itertools.islice(result, n)
        return result


@attrs(auto_attribs=True)
class Root:
    cities: Dict[str, City]
    venues: Dict[str, Venue]
    series: Dict[str, Series]

    # List of all events, sorted by date
    events: List[Event]

    default_timezone = tz.gettz('Europe/Prague')

    @classmethod
    def load(cls, data):
        if data['meta']['version'] != 2:
            raise ValueError('Can only load version 2')

        cities = {
            slug: City.load(c, slug)
            for slug, c in data['cities'].items()
        }
        venues = {}
        for city in cities.values():
            for slug, venue in city.venues.items():
                if slug in venues:
                    raise ValueError(f'duplicate venue slug: {slug}')
                venues[slug] = venue
        series = {
            slug: Series.load(s, slug, cities=cities, venues=venues)
            for slug, s in data['series'].items()
        }
        events = sorted(
            (
                event
                for the_series in series.values()
                for event in the_series.events
            ),
            key=lambda e: e.start,
        )
        self = cls(
            cities=cities,
            venues=venues,
            series=series,
            events=events,
        )
        typecheck(self)
        return self
