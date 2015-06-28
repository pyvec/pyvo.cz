import collections
from urllib.parse import urlparse, urljoin, urldefrag

import flask
import lxml.html
import requests


def test_homepage_ok(client):
    assert client.get('/').status_code == 200


def test_spider(client, monkeypatch, app, check_external_links):
    to_visit = {'http://localhost/'}
    visited = set()

    wanted_fragments = collections.defaultdict(list)

    def recording_url_for(*args, **kwargs):
        url = flask.url_for(*args, **kwargs)
        if url not in visited:
            to_visit.add(urljoin('http://localhost/', url))
        return url

    app.jinja_env.globals['url_for'] = recording_url_for

    while to_visit:
        url = to_visit.pop()
        visited.add(url)
        links = []
        parsed = urlparse(url)
        if parsed.netloc == 'localhost':
            print('visit', url)
            check_url(client, url, links)
            for link in links:
                fullurl = urljoin('http://localhost/', url)
                fullurl = urljoin(fullurl, link)
                result = urldefrag(fullurl)
                defrag = result.url
                fragment = result.fragment
                wanted_fragments[defrag].append(fragment)
                if defrag not in visited:
                    to_visit.add(defrag)
        else:
            if check_external_links and parsed.scheme in ('http', 'https'):
                print('check', url)
                check_external_link(url)
            else:
                print('ignore', url)


def check_url(client, url, links_out=None):
    if url == 'http://localhost/static/':
        return
    result = client.get(url)
    assert result.status_code == 200
    tree = lxml.html.document_fromstring(result.data)
    for element, attribute, link, pos in tree.iterlinks():
        if links_out is not None:
            links_out.append(link)


def check_external_link(url):
    assert requests.head(url).status_code in (200, 301, 302)
