
def test_404(client):
    result = client.get('http://localhost/nonexistent-city/')
    assert result.status_code == 404


# XXX: Check that site works with empty DB
