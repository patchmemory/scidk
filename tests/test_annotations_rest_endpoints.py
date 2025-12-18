import json

def test_annotations_crud_endpoints(client):
    # Create annotation
    payload = {"file_id": "fileX", "kind": "tag", "label": "Interesting", "note": "n1", "data_json": json.dumps({"k":1})}
    r = client.post('/api/annotations', json=payload)
    assert r.status_code == 201
    created = r.get_json()
    ann_id = created.get('id')
    assert isinstance(ann_id, int)

    # List annotations (paginated, no filter)
    rlist = client.get('/api/annotations?limit=10&offset=0')
    assert rlist.status_code == 200
    data = rlist.get_json()
    assert 'items' in data and isinstance(data['items'], list)
    assert any(it['id'] == ann_id for it in data['items'])

    # Get by id
    rget = client.get(f'/api/annotations/{ann_id}')
    assert rget.status_code == 200
    item = rget.get_json()
    assert item['id'] == ann_id and item['file_id'] == 'fileX'

    # Update (PATCH) allowed fields only
    up = {"label": "VeryInteresting", "note": "n2", "data_json": json.dumps({"k":2}), "file_id": "SHOULD_NOT_CHANGE"}
    rpatch = client.patch(f'/api/annotations/{ann_id}', json=up)
    assert rpatch.status_code == 200
    updated = rpatch.get_json()
    assert updated['label'] == 'VeryInteresting'
    assert updated['note'] == 'n2'
    assert updated['file_id'] == 'fileX'  # file_id must not change

    # Delete
    rdel = client.delete(f'/api/annotations/{ann_id}')
    assert rdel.status_code == 200
    rget2 = client.get(f'/api/annotations/{ann_id}')
    assert rget2.status_code == 404
