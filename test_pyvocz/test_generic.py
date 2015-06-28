import flask

def test_homepage_ok(client):
    assert client.get('/').status_code == 200

def test_spider(client, monkeypatch, app):
    to_visit = set('/')
    visited = set()

    def recording_url_for(*args, **kwargs):
        url = flask.url_for(*args, **kwargs)
        if url not in visited:
            to_visit.add(url)
        return url

    app.jinja_env.globals['url_for'] = recording_url_for

    while to_visit:
        url = to_visit.pop()
        visited.add(url)
        check_url(client, url)

def check_url(client, url):
    if url == '/static/':
        return
    result = client.get(url)
    assert result.status_code == 200
