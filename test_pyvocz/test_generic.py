import collections
from urllib.parse import urlparse, urljoin, urldefrag

import flask
import lxml.html
import requests


IGNORED_URLS = {
    'http://localhost/static/',
    'http://localhost/calendar/2030/',
    'http://localhost/calendar/2010/',
    'http://localhost/en/calendar/2030/',
    'http://localhost/en/calendar/2010/',

}

IGNORED_MIMETYPE_EXTENSIONS = {
    'image/vnd.microsoft.icon': 'ico',
    'image/x-icon': 'ico',
}


def test_homepage_ok(client):
    assert client.get('/').status_code == 200


def test_spider(client, app, check_external_links):
    """Check that all links work

    Spiders the site, making sure all internal links point to existing pages.
    Includes fragments: any #hash in a link must correspond to existing element
    with id.

    If check_external_links is true, checks external links as well.
    """
    to_visit = {'http://localhost/'}
    visited = set()
    external = set()

    wanted_fragments = collections.defaultdict(set)
    page_ids = {}

    def recording_url_for(*args, **kwargs):
        url = flask.url_for(*args, **kwargs)
        if url not in visited:
            to_visit.add(urljoin('http://localhost/', url))
        return url

    app.jinja_env.globals['url_for'] = recording_url_for

    while to_visit:
        url = to_visit.pop()
        if url in visited:
            continue
        visited.add(url)
        links = []
        parsed = urlparse(url)
        if parsed.netloc == 'localhost':
            print('visit', url)
            page_ids[url] = []
            check_url(client, url, links, page_ids[url])
            for link in links:
                fullurl = urljoin('http://localhost/', url)
                fullurl = urljoin(fullurl, link)
                result = urldefrag(fullurl)
                defrag = result.url
                fragment = result.fragment
                if fragment and urlparse(fullurl).netloc == 'localhost':
                    wanted_fragments[defrag].add(fragment)
                if defrag not in visited:
                    to_visit.add(defrag)
        else:
            if parsed.scheme in ('http', 'https'):
                external.add(url)
            else:
                print('ignore', url)

    for url, fragments in wanted_fragments.items():
        assert fragments <= set(page_ids[url])

    if check_external_links:
        for url in external:
            print('check', url)
            check_external_link(url)


def check_url(client, url, links_out=None, ids_out=None):
    if url in IGNORED_URLS:
        return

    base, dot, extension = url.rpartition('.')

    result = client.get(url)
    if dot and extension == IGNORED_MIMETYPE_EXTENSIONS.get(result.mimetype):
        return

    assert result.status_code in (200, 301, 302)
    tree = lxml.html.document_fromstring(result.data)
    if links_out is not None:
        for element, attribute, link, pos in tree.iterlinks():
            links_out.append(link)
    if ids_out is not None:
        for element in tree.cssselect('*[id]'):
            ids_out.append(element.attrib['id'])


def check_external_link(url):
    assert requests.head(url).status_code in (200, 301, 302)
