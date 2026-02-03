"""
Tests for annotations REST API endpoints.

Tests cover:
- Annotations CRUD (existing)
- POST /api/relationships - create relationships
- GET /api/relationships?file_id= - list relationships
- DELETE /api/relationships/<id> - delete relationship
- POST /api/sync - enqueue sync items
- GET /api/sync/queue - list sync queue
- POST /api/sync/<id>/mark-processed - mark sync item as processed
"""
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


# --- Relationships endpoints tests ---

def test_create_relationship_success(client):
    """Test creating a relationship with valid data."""
    response = client.post('/api/relationships', json={
        'from_id': 'file_abc123',
        'to_id': 'file_def456',
        'type': 'GENERATED_BY',
        'properties': {'confidence': 0.95, 'method': 'auto'}
    })

    assert response.status_code == 201
    data = response.get_json()
    assert 'id' in data
    assert data['from_id'] == 'file_abc123'
    assert data['to_id'] == 'file_def456'
    assert data['type'] == 'GENERATED_BY'
    assert data['properties_json'] is not None


def test_create_relationship_missing_fields(client):
    """Test creating relationship with missing required fields."""
    response = client.post('/api/relationships', json={
        'from_id': 'file_abc123',
        # missing to_id and type
    })

    assert response.status_code == 400
    data = response.get_json()
    assert data['status'] == 'error'
    assert 'Missing required fields' in data['error']


def test_list_relationships_success(client):
    """Test listing relationships for a file."""
    import uuid
    unique_id = f'file_test_{uuid.uuid4().hex[:8]}'

    # Create some relationships first
    client.post('/api/relationships', json={
        'from_id': unique_id + '_1',
        'to_id': unique_id,
        'type': 'LINKS_TO'
    })
    client.post('/api/relationships', json={
        'from_id': unique_id,
        'to_id': unique_id + '_2',
        'type': 'LINKS_TO'
    })

    # Query relationships for unique_id (appears in both)
    response = client.get(f'/api/relationships?file_id={unique_id}')

    assert response.status_code == 200
    data = response.get_json()
    assert 'relationships' in data
    assert data['count'] == 2
    assert data['file_id'] == unique_id


def test_list_relationships_missing_file_id(client):
    """Test listing relationships without file_id parameter."""
    response = client.get('/api/relationships')

    assert response.status_code == 400
    data = response.get_json()
    assert data['status'] == 'error'


def test_delete_relationship_success(client):
    """Test deleting a relationship."""
    # Create a relationship
    create_response = client.post('/api/relationships', json={
        'from_id': 'file_delete1',
        'to_id': 'file_delete2',
        'type': 'TEST_RELATION'
    })
    rel_id = create_response.get_json()['id']

    # Delete it
    delete_response = client.delete(f'/api/relationships/{rel_id}')

    assert delete_response.status_code == 200
    data = delete_response.get_json()
    assert data['status'] == 'deleted'
    assert data['id'] == rel_id


# --- Sync queue endpoints tests ---

def test_enqueue_sync_success(client):
    """Test enqueueing a sync item."""
    response = client.post('/api/sync', json={
        'entity_type': 'relationship',
        'entity_id': '123',
        'action': 'create',
        'payload': {'target': 'neo4j', 'batch': True}
    })

    assert response.status_code == 201
    data = response.get_json()
    assert data['status'] == 'enqueued'
    assert 'sync_id' in data
    assert data['entity_type'] == 'relationship'
    assert data['entity_id'] == '123'
    assert data['action'] == 'create'


def test_enqueue_sync_missing_fields(client):
    """Test enqueueing sync with missing required fields."""
    response = client.post('/api/sync', json={
        'entity_type': 'relationship',
        # missing entity_id and action
    })

    assert response.status_code == 400
    data = response.get_json()
    assert data['status'] == 'error'


def test_list_sync_queue(client):
    """Test listing sync queue items."""
    # Enqueue some items
    for i in range(3):
        client.post('/api/sync', json={
            'entity_type': 'test',
            'entity_id': f'item_{i}',
            'action': 'test_action'
        })

    # List queue
    response = client.get('/api/sync/queue')

    assert response.status_code == 200
    data = response.get_json()
    assert 'queue' in data
    assert data['count'] >= 3


def test_mark_sync_processed_success(client):
    """Test marking a sync item as processed."""
    # Enqueue an item
    enqueue_response = client.post('/api/sync', json={
        'entity_type': 'test',
        'entity_id': 'mark_test',
        'action': 'test_action'
    })
    sync_id = enqueue_response.get_json()['sync_id']

    # Mark as processed
    mark_response = client.post(f'/api/sync/{sync_id}/mark-processed')

    assert mark_response.status_code == 200
    data = mark_response.get_json()
    assert data['status'] == 'marked_processed'
    assert data['id'] == sync_id


def test_privacy_guardrails_documented(client):
    """
    Note: Privacy guardrails for annotations endpoints.

    In production, these endpoints should enforce:
    1. Authentication: Only authenticated users can access
    2. Authorization: Users can only access their own data or shared projects
    3. Rate limiting: Prevent abuse
    4. Input validation: Sanitize all inputs
    5. Audit logging: Track all relationship changes

    This test documents the requirement. Future phases should add security layers.
    """
    assert True, "Privacy guardrails documented for future implementation"
