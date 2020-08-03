import textwrap
import collections
from urllib.parse import urlencode


URL = 'https://github.com/pyvec/pyvo-data/new/master/series/{series}/events/f?{params}'


def event_add_link(series):
    """Generate a GitHub URL for adding a new event at the given date"""

    city_slug = '...'
    venue_slug = '...'
    number = ''
    next_date = '...'
    next_datetime = '...'

    if series.events:
        last_event = series.events[-1]
        city_slug = last_event.city.slug
        if last_event.number:
            number = f'number: {last_event.number + 1}'

        c = collections.Counter(
            e.venue.slug for e in series.events[-12:] if e.venue
        )
        most_common = [k for k, n in c.most_common(5)]
        if most_common:
            venue_slug = most_common[0]
            if len(most_common) > 1:
                venue_slug += '   # ' + ', '.join(most_common[1:]) + ' ?'

    if series.recurrence_rule:
        occurrences = list(series.next_occurrences(1))
        if occurrences:
            occurrence = occurrences[0]
            next_datetime = occurrence.replace(tzinfo=None).isoformat(' ')
            next_date = occurrence.date().isoformat()

    params = {
        'filename': f'{next_date}.yaml',
        'value': textwrap.dedent(f"""\
            name: {series.name}
            city: {city_slug}
            venue: {venue_slug}
            start: {next_datetime}
            # topic: ...
            {number}
            description: |
                ...

            talks:
              - title: ...
                description: |
                    ...
                lightning: false
                speakers:
                    - ...
                    - ...
        """),
        'message': f'{series.home_city.name}: Add entry for {next_date}',
    }

    return URL.format(series=series.slug, params=urlencode(params), next_date=next_date)
