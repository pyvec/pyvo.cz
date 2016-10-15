import re

from flask import g, url_for
from jinja2 import escape
from markupsafe import Markup

__all__ = ('mail_link', 'nl2br', 'monthname', 'shortdayname', 'shortmonth',
           'shortday', 'longdate', 'dayname', 'th', 'event_url', 'event_link')

_paragraph_re = re.compile(r'(?:\r\n|\r|\n){2,}')

def mail_link(address):
    address = address.replace('a', '&#97;')
    address = address.replace('c', '&#99;')
    address = address.replace('.', '&#46;')
    a = address.replace('@', '&#64;')
    b = address.replace('@', '&#64;<!--==≡≡==-->')
    return Markup('<a href="m&#97;ilto://{}">{}</a>'.format(a, b))


def nl2br(value):
    result = u'\n\n'.join(u'<p>%s</p>' % p.replace('\n', '<br>\n') \
        for p in _paragraph_re.split(escape(value)))
    result = Markup(result)
    return result


def monthname(value, case='nominative'):
    if g.lang_code == 'cs':
        if case == 'nominative':
            list = ['Leden', 'Únor', 'Březen', 'Duben', 'Květen', 'Červen',
                    'Červenec', 'Srpen', 'Září', 'Říjen', 'Listopad',
                    'Prosinec']
        if case == 'genitive':
            list = ['Ledna', 'Února', 'Března', 'Dubna', 'Května', 'Června',
                    'Července', 'Srpna', 'Září', 'Října', 'Listopadu',
                    'Prosince']
    elif g.lang_code == 'en':
        list = ['January', 'February', 'March', 'April', 'May', 'June', 'July',
                'August', 'September', 'October', 'November', 'December']
    else:
        raise ValueError('unknown lang_code')
    return list[value - 1]


def dayname(value, preposition=None):
    if g.lang_code == 'cs':
        names = ['v pondělí', 'v úterý', 've středu', 've čtvrtek', 'v pátek',
                 'v sobotu', 'v neděli']
        name = names[value % 7]
        if preposition is None:
            return name.split()[-1]
        elif preposition == 'v':
            return name
        else:
            raise ValueError('unknown preposition')
    elif g.lang_code == 'en':
        names = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday',
                 'Saturday', 'Sunday']
        return names[value % 7]
    raise ValueError('unknown lang_code')


def shortdayname(value):
    if g.lang_code == 'cs':
        return ['Po', 'Út', 'St', 'Čt', 'Pá', 'So', 'Ne'][value % 7]
    elif g.lang_code == 'en':
        return ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'][value % 7]
    raise ValueError('unknown lang_code')


def shortmonth(value):
    if g.lang_code == 'cs':
        return value
    elif g.lang_code == 'en':
        return ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep',
                'Oct', 'Nov', 'Dec'][value - 1]
    raise ValueError(value)


def shortday(value):
    if g.lang_code == 'cs':
        return '{}. {}.'.format(value.day, value.month)
    elif g.lang_code == 'en':
        return '{} {}'.format(shortmonth(value.month), value.day)
    raise ValueError(value)


def longdate(value):
    if g.lang_code == 'cs':
        return '{}. {}. {}'.format(value.day, value.month, value.year)
    elif g.lang_code == 'en':
        return '{} {} {}'.format(monthname(value.month), value.day, value.year)
    raise ValueError(value)


def th(value):
    if g.lang_code == 'cs':
        raise ValueError('th does not make sense for Czech')
    elif g.lang_code == 'en':
        if value % 10 == 1:
            return '{} st'
        elif value % 10 == 2:
            return 'nd'
        elif value % 10 == 3:
            return 'rd'
        else:
            return 'th'


def event_url(event):
    return url_for('event', cityslug=event.city.slug,
                   date_slug='{0.year:4}-{0.month:02}'.format(event.date))


def event_link(event, *, text=None):
    if text is None:
        text = event.title
    return Markup('<a href="{}">{}</a>'.format(event_url(event), text))
