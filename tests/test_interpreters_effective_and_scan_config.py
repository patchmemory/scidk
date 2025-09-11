import os
from scidk.app import create_app


def test_effective_default_and_scan_config(monkeypatch, tmp_path):
    # Ensure no env overrides
    monkeypatch.delenv('SCIDK_ENABLE_INTERPRETERS', raising=False)
    monkeypatch.delenv('SCIDK_DISABLE_INTERPRETERS', raising=False)

    app = create_app(); app.config.update({"TESTING": True})
    client = app.test_client()
    # Effective default
    r = client.get('/api/interpreters?view=effective')
    assert r.status_code == 200
    eff = {it['id']: (it['enabled'], it['source']) for it in r.get_json()}
    assert 'python_code' in eff
    assert eff['python_code'][1] == 'default'

    # Trigger a local_fs scan to capture config_json
    resp = client.post('/api/tasks', json={"type": "scan", "provider_id": "local_fs", "path": str(tmp_path), "recursive": False})
    assert resp.status_code in (200, 202)
    # Poll task list quickly by checking scans registry directly
    scans = app.extensions['scidk']['scans']
    # Wait a short while if needed
    import time
    for _ in range(50):
        if scans:
            break
        time.sleep(0.02)
    assert scans, "Expected a scan to be registered"
    scan = next(iter(scans.values()))
    cfg = scan.get('config_json') or {}
    assert 'interpreters' in cfg
    inter = cfg['interpreters']
    assert isinstance(inter.get('effective_enabled'), list)
    assert inter.get('source') in ('default', 'global', 'cli')


def test_effective_env_cli_overrides(monkeypatch):
    # Override via env to simulate CLI flags
    monkeypatch.setenv('SCIDK_ENABLE_INTERPRETERS', 'csv')
    monkeypatch.setenv('SCIDK_DISABLE_INTERPRETERS', 'python_code')
    app = create_app(); app.config.update({"TESTING": True})
    client = app.test_client()
    r = client.get('/api/interpreters?view=effective')
    assert r.status_code == 200
    items = r.get_json()
    by_id = {it['id']: it for it in items}
    assert by_id['csv']['enabled'] is True
    assert by_id['python_code']['enabled'] is False
    assert by_id['csv']['source'] == 'cli'
