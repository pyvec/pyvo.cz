import re

from jinja2 import escape
from markupsafe import Markup

__all__ = 'mail_link', 'nl2br'

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
