def test_homepage_ok(client):
    assert client.get('/').status_code == 200
