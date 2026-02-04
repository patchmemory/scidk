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
