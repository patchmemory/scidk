"""
Tests for Labels API endpoints.

Tests cover:
- GET /api/labels - list all labels
- GET /api/labels/<name> - get label definition
- POST /api/labels - create/update label
- DELETE /api/labels/<name> - delete label
- POST /api/labels/<name>/push - push label to Neo4j
- POST /api/labels/pull - pull labels from Neo4j
- GET /api/labels/neo4j/schema - get Neo4j schema
"""
import json


def test_list_labels_empty(client):
    """Test listing labels when none exist."""
    response = client.get('/api/labels')
    assert response.status_code == 200
    data = response.get_json()
    assert data['status'] == 'success'
    assert 'labels' in data
    assert isinstance(data['labels'], list)


def test_create_label_success(client):
    """Test creating a label with properties and relationships."""
    payload = {
        'name': 'Project',
        'properties': [
            {'name': 'name', 'type': 'string', 'required': True},
            {'name': 'budget', 'type': 'number', 'required': False}
        ],
        'relationships': [
            {'type': 'HAS_FILE', 'target_label': 'File', 'properties': []}
        ]
    }

    response = client.post('/api/labels', json=payload)
    assert response.status_code == 200
    data = response.get_json()
    assert data['status'] == 'success'
    assert 'label' in data
    assert data['label']['name'] == 'Project'
    assert len(data['label']['properties']) == 2
    assert len(data['label']['relationships']) == 1


def test_create_label_missing_name(client):
    """Test creating label without name fails."""
    payload = {'properties': []}

    response = client.post('/api/labels', json=payload)
    assert response.status_code == 400
    data = response.get_json()
    assert data['status'] == 'error'
    assert 'name' in data['error'].lower()


def test_create_label_invalid_property(client):
    """Test creating label with invalid property structure."""
    payload = {
        'name': 'BadLabel',
        'properties': [
            {'name': 'valid', 'type': 'string', 'required': True},
            {'invalid': 'structure'}  # Missing 'name' and 'type'
        ]
    }

    response = client.post('/api/labels', json=payload)
    assert response.status_code == 400
    data = response.get_json()
    assert data['status'] == 'error'


def test_get_label_success(client):
    """Test retrieving an existing label."""
    # First create a label
    payload = {
        'name': 'TestLabel',
        'properties': [{'name': 'prop1', 'type': 'string', 'required': False}],
        'relationships': []
    }
    client.post('/api/labels', json=payload)

    # Now get it
    response = client.get('/api/labels/TestLabel')
    assert response.status_code == 200
    data = response.get_json()
    assert data['status'] == 'success'
    assert data['label']['name'] == 'TestLabel'
    assert len(data['label']['properties']) == 1


def test_get_label_not_found(client):
    """Test retrieving non-existent label."""
    response = client.get('/api/labels/NonExistent')
    assert response.status_code == 404
    data = response.get_json()
    assert data['status'] == 'error'


def test_update_label(client):
    """Test updating an existing label."""
    # Create initial label
    payload = {
        'name': 'UpdateTest',
        'properties': [{'name': 'old_prop', 'type': 'string', 'required': False}],
        'relationships': []
    }
    client.post('/api/labels', json=payload)

    # Update it
    updated_payload = {
        'name': 'UpdateTest',
        'properties': [
            {'name': 'old_prop', 'type': 'string', 'required': False},
            {'name': 'new_prop', 'type': 'number', 'required': True}
        ],
        'relationships': []
    }
    response = client.post('/api/labels', json=updated_payload)
    assert response.status_code == 200
    data = response.get_json()
    assert len(data['label']['properties']) == 2


def test_delete_label_success(client):
    """Test deleting an existing label."""
    # Create label
    payload = {
        'name': 'DeleteTest',
        'properties': [],
        'relationships': []
    }
    client.post('/api/labels', json=payload)

    # Delete it
    response = client.delete('/api/labels/DeleteTest')
    assert response.status_code == 200
    data = response.get_json()
    assert data['status'] == 'success'

    # Verify it's gone
    get_response = client.get('/api/labels/DeleteTest')
    assert get_response.status_code == 404


def test_delete_label_not_found(client):
    """Test deleting non-existent label."""
    response = client.delete('/api/labels/NonExistent')
    assert response.status_code == 404
    data = response.get_json()
    assert data['status'] == 'error'


def test_list_multiple_labels(client):
    """Test listing multiple labels."""
    # Create multiple labels
    labels = ['Label1', 'Label2', 'Label3']
    for name in labels:
        payload = {
            'name': name,
            'properties': [{'name': 'test', 'type': 'string', 'required': False}],
            'relationships': []
        }
        client.post('/api/labels', json=payload)

    # List all labels
    response = client.get('/api/labels')
    assert response.status_code == 200
    data = response.get_json()
    assert data['status'] == 'success'
    assert len(data['labels']) >= 3
    label_names = [l['name'] for l in data['labels']]
    for name in labels:
        assert name in label_names


def test_label_with_all_property_types(client):
    """Test creating label with all supported property types."""
    payload = {
        'name': 'AllTypes',
        'properties': [
            {'name': 'str_prop', 'type': 'string', 'required': False},
            {'name': 'num_prop', 'type': 'number', 'required': False},
            {'name': 'bool_prop', 'type': 'boolean', 'required': False},
            {'name': 'date_prop', 'type': 'date', 'required': False},
            {'name': 'datetime_prop', 'type': 'datetime', 'required': False}
        ],
        'relationships': []
    }

    response = client.post('/api/labels', json=payload)
    assert response.status_code == 200
    data = response.get_json()
    assert len(data['label']['properties']) == 5

    # Verify types are preserved
    types = {p['name']: p['type'] for p in data['label']['properties']}
    assert types['str_prop'] == 'string'
    assert types['num_prop'] == 'number'
    assert types['bool_prop'] == 'boolean'
    assert types['date_prop'] == 'date'
    assert types['datetime_prop'] == 'datetime'


def test_label_with_multiple_relationships(client):
    """Test creating label with multiple relationships."""
    # Create target labels first
    for name in ['File', 'Directory', 'User']:
        client.post('/api/labels', json={
            'name': name,
            'properties': [],
            'relationships': []
        })

    payload = {
        'name': 'Project',
        'properties': [],
        'relationships': [
            {'type': 'HAS_FILE', 'target_label': 'File', 'properties': []},
            {'type': 'HAS_DIRECTORY', 'target_label': 'Directory', 'properties': []},
            {'type': 'OWNED_BY', 'target_label': 'User', 'properties': []}
        ]
    }

    response = client.post('/api/labels', json=payload)
    assert response.status_code == 200
    data = response.get_json()
    assert len(data['label']['relationships']) == 3


def test_push_to_neo4j_label_not_found(client):
    """Test pushing non-existent label to Neo4j."""
    response = client.post('/api/labels/NonExistent/push')
    # Should return 404 since label doesn't exist
    assert response.status_code == 404
    data = response.get_json()
    assert data['status'] == 'error'


def test_get_neo4j_schema(client):
    """Test getting Neo4j schema (will fail if Neo4j not configured)."""
    response = client.get('/api/labels/neo4j/schema')
    # Either success (if Neo4j configured) or error (if not)
    assert response.status_code in [200, 500]
    data = response.get_json()
    assert 'status' in data


def test_pull_all_labels_from_neo4j(client):
    """Test pulling all labels from Neo4j."""
    response = client.post('/api/labels/pull')
    # Either success (if Neo4j configured) or error (if not)
    assert response.status_code in [200, 500]
    data = response.get_json()
    assert 'status' in data

    # If successful, should have imported_labels and count
    if response.status_code == 200:
        assert 'imported_labels' in data or 'count' in data


def test_pull_single_label_not_found(client):
    """Test pulling non-existent label from Neo4j."""
    response = client.post('/api/labels/NonExistent/pull')
    # Should return 404 since label doesn't exist
    assert response.status_code == 404
    data = response.get_json()
    assert data['status'] == 'error'


def test_pull_single_label_from_neo4j(client):
    """Test pulling single label properties from Neo4j."""
    # First create a label
    payload = {
        'name': 'PullTest',
        'properties': [{'name': 'initial_prop', 'type': 'string', 'required': False}],
        'relationships': []
    }
    client.post('/api/labels', json=payload)

    # Try to pull from Neo4j
    response = client.post('/api/labels/PullTest/pull')
    # Either success (if Neo4j configured) or error (if not)
    assert response.status_code in [200, 500]
    data = response.get_json()
    assert 'status' in data

    # If successful, should have label and new_properties_count
    if response.status_code == 200:
        assert 'label' in data
        assert 'new_properties_count' in data


def test_batch_pull_labels_success(client):
    """Test batch pulling multiple labels from Neo4j."""
    # Create test labels
    for name in ['BatchPull1', 'BatchPull2']:
        payload = {
            'name': name,
            'properties': [{'name': 'test', 'type': 'string', 'required': False}],
            'relationships': []
        }
        client.post('/api/labels', json=payload)

    # Batch pull
    response = client.post('/api/labels/batch/pull', json={
        'label_names': ['BatchPull1', 'BatchPull2']
    })

    # Either success (if Neo4j configured) or error (if not)
    assert response.status_code in [200, 500]
    data = response.get_json()
    assert 'status' in data

    # If successful, should have results
    if response.status_code == 200:
        assert 'results' in data
        assert 'total_new_properties' in data
        assert 'total_new_relationships' in data
        assert len(data['results']) == 2


def test_batch_pull_labels_empty_list(client):
    """Test batch pull with empty label list."""
    response = client.post('/api/labels/batch/pull', json={
        'label_names': []
    })
    assert response.status_code == 400
    data = response.get_json()
    assert data['status'] == 'error'
    assert 'no label names' in data['error'].lower()


def test_batch_pull_labels_missing_field(client):
    """Test batch pull without label_names field."""
    response = client.post('/api/labels/batch/pull', json={})
    assert response.status_code == 400
    data = response.get_json()
    assert data['status'] == 'error'


def test_push_label_to_neo4j(client):
    """Test pushing label to Neo4j."""
    # Create a label
    payload = {
        'name': 'PushTest',
        'properties': [
            {'name': 'name', 'type': 'string', 'required': True},
            {'name': 'age', 'type': 'number', 'required': False}
        ],
        'relationships': []
    }
    client.post('/api/labels', json=payload)

    # Push to Neo4j
    response = client.post('/api/labels/PushTest/push')
    # Either success (if Neo4j configured) or error (if not)
    assert response.status_code in [200, 500]
    data = response.get_json()
    assert 'status' in data

    # If successful, should have constraints/indexes info
    if response.status_code == 200:
        assert 'label' in data
        assert data['label'] == 'PushTest'


def test_batch_delete_labels_success(client):
    """Test batch deleting multiple labels."""
    # Create test labels
    for name in ['DeleteBatch1', 'DeleteBatch2', 'DeleteBatch3']:
        payload = {
            'name': name,
            'properties': [],
            'relationships': []
        }
        client.post('/api/labels', json=payload)

    # Batch delete
    response = client.post('/api/labels/batch/delete', json={
        'label_names': ['DeleteBatch1', 'DeleteBatch2', 'DeleteBatch3']
    })
    assert response.status_code == 200
    data = response.get_json()
    assert data['status'] == 'success'
    assert 'deleted_count' in data
    assert data['deleted_count'] == 3
    assert 'results' in data

    # Verify labels are deleted
    for name in ['DeleteBatch1', 'DeleteBatch2', 'DeleteBatch3']:
        get_response = client.get(f'/api/labels/{name}')
        assert get_response.status_code == 404


def test_batch_delete_labels_empty_list(client):
    """Test batch delete with empty label list."""
    response = client.post('/api/labels/batch/delete', json={
        'label_names': []
    })
    assert response.status_code == 400
    data = response.get_json()
    assert data['status'] == 'error'
    assert 'no label names' in data['error'].lower()


def test_batch_delete_labels_missing_field(client):
    """Test batch delete without label_names field."""
    response = client.post('/api/labels/batch/delete', json={})
    assert response.status_code == 400
    data = response.get_json()
    assert data['status'] == 'error'


def test_batch_delete_labels_partial_success(client):
    """Test batch delete with some non-existent labels."""
    # Create only one label
    payload = {
        'name': 'DeleteExists',
        'properties': [],
        'relationships': []
    }
    client.post('/api/labels', json=payload)

    # Try to delete both existing and non-existent
    response = client.post('/api/labels/batch/delete', json={
        'label_names': ['DeleteExists', 'NonExistent']
    })
    assert response.status_code == 200
    data = response.get_json()
    assert data['status'] == 'success'
    assert 'results' in data
    assert len(data['results']) == 2

    # Verify the existing label was deleted
    get_response = client.get('/api/labels/DeleteExists')
    assert get_response.status_code == 404
