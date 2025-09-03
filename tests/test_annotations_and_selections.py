import json
import time
from scidk.app import create_app


def test_create_selection_and_items(client):
    # Create selection
    r = client.post('/api/selections', json={'name': 'My Selection'})
    assert r.status_code == 201
    data = r.get_json()
    sel_id = data['id']
    assert sel_id
    # Add items
    r2 = client.post(f'/api/selections/{sel_id}/items', json={'file_ids': ['file1', 'file2']})
    assert r2.status_code == 200
    d2 = r2.get_json()
    assert d2['selection_id'] == sel_id
    assert d2['added'] >= 2


def test_create_and_get_annotations(client):
    now = time.time()
    # Create annotation
    payload = {
        'file_id': 'fileA',
        'kind': 'tag',
        'label': 'important',
        'note': 'check this later',
        'data_json': json.dumps({'a': 1})
    }
    r = client.post('/api/annotations', json=payload)
    assert r.status_code == 201
    created = r.get_json()
    assert created['file_id'] == 'fileA'
    assert created['kind'] == 'tag'
    # Fetch by file_id
    r2 = client.get('/api/annotations?file_id=fileA')
    assert r2.status_code == 200
    body = r2.get_json()
    assert body['count'] >= 1
    assert any(item['label'] == 'important' for item in body['items'])
