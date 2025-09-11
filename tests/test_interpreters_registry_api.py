import json
from scidk.app import create_app

def test_api_interpreters_schema():
    app = create_app(); app.config.update({"TESTING": True})
    client = app.test_client()
    resp = client.get('/api/interpreters')
    assert resp.status_code == 200
    data = resp.get_json()
    assert isinstance(data, list)
    assert any(it.get('id') == 'python_code' for it in data)
    # Validate required fields exist for each item
    for it in data:
        assert 'id' in it
        assert 'version' in it
        assert 'globs' in it
        assert 'default_enabled' in it
        assert 'cost' in it  # may be None
    # Effective view placeholder
    resp2 = client.get('/api/interpreters?view=effective')
    assert resp2.status_code == 200
    eff = resp2.get_json()
    assert isinstance(eff, list)
    for it in eff:
        assert 'enabled' in it
        assert 'source' in it
