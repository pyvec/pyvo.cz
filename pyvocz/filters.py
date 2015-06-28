import re

from flask import g
from jinja2 import escape
from markupsafe import Markup

__all__ = ('mail_link', 'nl2br', 'monthname', 'shortdayname', 'shortmonth',
           'shortday', 'longdate')

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


def monthname(value):
    if g.lang_code == 'cs':
        list = ['Leden', 'Únor', 'Březen', 'Duben', 'Květen', 'Červen',
                'Červenec', 'Srpen', 'Září', 'Říjen', 'Listopad', 'Prosinec']
    elif g.lang_code == 'en':
        list = ['January', 'February', 'March', 'April', 'May', 'June', 'July',
                'August', 'September', 'October', 'November', 'December']
    else:
        raise ValueError(value)
    return list[value - 1]


def shortdayname(value):
    if g.lang_code == 'cs':
        return ['Po', 'Út', 'St', 'Čt', 'Pá', 'So', 'Ne'][value % 7]
    elif g.lang_code == 'en':
        return ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'][value % 7]
    raise ValueError(value)


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
