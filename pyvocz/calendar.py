import datetime
import collections

from czech_holidays import Holidays
from dateutil.relativedelta import relativedelta

DAY = datetime.timedelta(days=1)
WEEK = DAY * 7
firstweekday=None
def get_calendar(
    db, first_year=None, first_month=None, num_months=3, series_slugs=None,
):
    if first_year is None:
        first_year = datetime.datetime.now().year
    if first_month is None:
        first_month = datetime.datetime.now().month - num_months // 2
    while first_month < 1:
        first_month += 12
        first_year -= 1
    while first_month > 12:
        first_month -= 12
        first_year += 1

    next_occurences = collections.defaultdict(list)

    start = datetime.date(year=first_year, month=first_month, day=1)
    end = start + relativedelta(months=num_months)

    if series_slugs is None:
        series_slugs = list(db.series)
    for series_slug in series_slugs:
        series = db.series.get(series_slug)
        if not series:
            continue
        next_occurrences = series.next_occurrences()
        zero_time = datetime.time(tzinfo=db.default_timezone)
        start_date = datetime.datetime.combine(start, zero_time)
        end_date = datetime.datetime.combine(end+relativedelta(days=1),
                                                zero_time)
        between = getattr(next_occurrences, 'between', None)
        if between:
            occurences = between(start_date, end_date, inc=True)
            for occurence in occurences:
                next_occurences[occurence.date()].append(series)

    events = collections.defaultdict(list)
    for event in db.events:
        if series_slugs is not None and event.series.slug not in series_slugs:
            continue
        if event.date >= start and event.date < end:
            events[event.date].append(event)

    months = collections.OrderedDict()
    now = start
    while now < end:
        months[now.year, now.month] = get_month(now.year, now.month, events,
                                                next_occurences)
        now += relativedelta(months=1)

    return months

def get_month(year, month, events, next_occurences=None):
    holidays = {h: h for h in Holidays(year)}
    def mkday(day):
        alien = (day.month != month)
        return get_day(day, events=events, holidays=holidays, alien=alien,
                       next_occurences=next_occurences)

    first_of_month = datetime.date(year, month, 1)
    first = first_of_month - DAY * first_of_month.weekday()

    last = first
    while (last.year, last.month) <= (year, month):
        last += WEEK

    while (last - first) < 6 * WEEK:
        last += WEEK

    week = []
    weeks = []
    current = first
    while current < last:
        if current.weekday() == 0:
            week = []
            weeks.append(week)
        week.append(mkday(current))
        current += DAY

    return weeks


def get_day(day, events, holidays, next_occurences=None, *, alien=False):
    return {
        'day': day,
        'events': events[day],
        'holiday': holidays.get(day),
        'weekend': day.weekday() >= 5,
        'next_occurences': next_occurences.get(day) if next_occurences else [],
        'alien': alien,
    }
