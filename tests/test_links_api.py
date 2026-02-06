"""
Tests for Links API endpoints.

Tests cover:
- GET /api/links - list all link definitions
- GET /api/links/<id> - get link definition
- POST /api/links - create/update link definition
- DELETE /api/links/<id> - delete link definition
- POST /api/links/<id>/preview - preview link matches
- POST /api/links/<id>/execute - execute link job
- GET /api/links/jobs/<job_id> - get job status
- GET /api/links/jobs - list jobs
- GET /api/links/available-labels - get available labels for dropdowns
- POST /api/links/migrate - migrate existing links to Label→Label model
"""
import json
import pytest


def test_list_links_empty(client):
    """Test listing links when none exist."""
    response = client.get('/api/links')
    assert response.status_code == 200
    data = response.get_json()
    assert data['status'] == 'success'
    assert 'links' in data
    assert isinstance(data['links'], list)


def test_create_link_success(client):
    """Test creating a link definition with all required fields (Label→Label model)."""
    # Create labels first
    client.post('/api/labels', json={
        'name': 'Author',
        'properties': [{'name': 'email', 'type': 'string'}],
        'relationships': []
    })
    client.post('/api/labels', json={
        'name': 'File',
        'properties': [{'name': 'path', 'type': 'string'}],
        'relationships': []
    })

    payload = {
        'name': 'Authors to Files',
        'source_label': 'Author',
        'target_label': 'File',
        'match_strategy': 'table_import',
        'match_config': {
            'table_data': 'name,email,file_path\nAlice,alice@ex.com,file1.txt'
        },
        'relationship_type': 'AUTHORED',
        'relationship_props': {
            'date': '2024-01-15'
        }
    }

    response = client.post('/api/links', json=payload)
    assert response.status_code == 200
    data = response.get_json()
    assert data['status'] == 'success'
    assert 'link' in data
    assert data['link']['name'] == 'Authors to Files'
    assert data['link']['source_label'] == 'Author'
    assert data['link']['target_label'] == 'File'
    assert data['link']['match_strategy'] == 'table_import'
    assert data['link']['relationship_type'] == 'AUTHORED'
    assert 'id' in data['link']


def test_create_link_missing_name(client):
    """Test creating link without name fails."""
    payload = {
        'source_type': 'graph',
        'target_type': 'label',
        'match_strategy': 'property',
        'relationship_type': 'RELATED'
    }

    response = client.post('/api/links', json=payload)
    assert response.status_code == 400
    data = response.get_json()
    assert data['status'] == 'error'
    assert 'name' in data['error'].lower()


def test_create_link_invalid_source_type(client):
    """Test creating link without source_label fails (Label→Label model)."""
    payload = {
        'name': 'Bad Link',
        'target_label': 'File',
        'match_strategy': 'property',
        'relationship_type': 'RELATED'
    }

    response = client.post('/api/links', json=payload)
    assert response.status_code == 400
    data = response.get_json()
    assert data['status'] == 'error'
    assert 'source_label' in data['error'].lower()


def test_create_link_invalid_target_type(client):
    """Test creating link without target_label fails (Label→Label model)."""
    payload = {
        'name': 'Bad Link',
        'source_label': 'Person',
        'match_strategy': 'property',
        'relationship_type': 'RELATED'
    }

    response = client.post('/api/links', json=payload)
    assert response.status_code == 400
    data = response.get_json()
    assert data['status'] == 'error'
    assert 'target_label' in data['error'].lower()


def test_create_link_invalid_match_strategy(client):
    """Test creating link with invalid match_strategy fails."""
    # Create labels first
    client.post('/api/labels', json={
        'name': 'TestLabel',
        'properties': [],
        'relationships': []
    })

    payload = {
        'name': 'Bad Link',
        'source_label': 'TestLabel',
        'target_label': 'TestLabel',
        'match_strategy': 'invalid',
        'relationship_type': 'RELATED'
    }

    response = client.post('/api/links', json=payload)
    assert response.status_code == 400
    data = response.get_json()
    assert data['status'] == 'error'
    assert 'match_strategy' in data['error'].lower()


def test_create_link_missing_relationship_type(client):
    """Test creating link without relationship_type fails."""
    # Create labels first
    client.post('/api/labels', json={
        'name': 'Person',
        'properties': [],
        'relationships': []
    })

    payload = {
        'name': 'Bad Link',
        'source_label': 'Person',
        'target_label': 'Person',
        'match_strategy': 'property'
    }

    response = client.post('/api/links', json=payload)
    assert response.status_code == 400
    data = response.get_json()
    assert data['status'] == 'error'
    assert 'relationship_type' in data['error'].lower()


def test_get_link_success(client):
    """Test retrieving an existing link definition."""
    # Create labels first
    client.post('/api/labels', json={
        'name': 'Person',
        'properties': [{'name': 'email', 'type': 'string'}],
        'relationships': []
    })
    client.post('/api/labels', json={
        'name': 'File',
        'properties': [{'name': 'path', 'type': 'string'}],
        'relationships': []
    })

    # Create a link
    payload = {
        'name': 'Test Link',
        'source_label': 'Person',
        'target_label': 'File',
        'match_strategy': 'property',
        'match_config': {'source_field': 'email', 'target_field': 'author'},
        'relationship_type': 'AUTHORED',
        'relationship_props': {}
    }
    create_response = client.post('/api/links', json=payload)
    link_id = create_response.get_json()['link']['id']

    # Now get it
    response = client.get(f'/api/links/{link_id}')
    assert response.status_code == 200
    data = response.get_json()
    assert data['status'] == 'success'
    assert data['link']['name'] == 'Test Link'
    assert data['link']['id'] == link_id


def test_get_link_not_found(client):
    """Test retrieving non-existent link."""
    response = client.get('/api/links/nonexistent-id')
    assert response.status_code == 404
    data = response.get_json()
    assert data['status'] == 'error'


def test_update_link_success(client):
    """Test updating an existing link definition."""
    # Create labels first
    client.post('/api/labels', json={
        'name': 'Person',
        'properties': [{'name': 'email', 'type': 'string'}],
        'relationships': []
    })
    client.post('/api/labels', json={
        'name': 'File',
        'properties': [{'name': 'path', 'type': 'string'}],
        'relationships': []
    })

    # Create a link
    payload = {
        'name': 'Original Name',
        'source_label': 'Person',
        'target_label': 'File',
        'match_strategy': 'property',
        'match_config': {'source_field': 'email', 'target_field': 'author'},
        'relationship_type': 'AUTHORED',
        'relationship_props': {}
    }
    create_response = client.post('/api/links', json=payload)
    link_id = create_response.get_json()['link']['id']

    # Update it
    update_payload = payload.copy()
    update_payload['id'] = link_id
    update_payload['name'] = 'Updated Name'

    response = client.post('/api/links', json=update_payload)
    assert response.status_code == 200
    data = response.get_json()
    assert data['status'] == 'success'
    assert data['link']['name'] == 'Updated Name'
    assert data['link']['id'] == link_id


def test_delete_link_success(client):
    """Test deleting a link definition."""
    # Create labels first
    client.post('/api/labels', json={
        'name': 'Person',
        'properties': [{'name': 'email', 'type': 'string'}],
        'relationships': []
    })
    client.post('/api/labels', json={
        'name': 'File',
        'properties': [{'name': 'path', 'type': 'string'}],
        'relationships': []
    })

    # Create a link
    payload = {
        'name': 'To Delete',
        'source_label': 'Person',
        'target_label': 'File',
        'match_strategy': 'property',
        'match_config': {'source_field': 'email', 'target_field': 'author'},
        'relationship_type': 'AUTHORED',
        'relationship_props': {}
    }
    create_response = client.post('/api/links', json=payload)
    link_id = create_response.get_json()['link']['id']

    # Delete it
    response = client.delete(f'/api/links/{link_id}')
    assert response.status_code == 200
    data = response.get_json()
    assert data['status'] == 'success'

    # Verify it's gone
    get_response = client.get(f'/api/links/{link_id}')
    assert get_response.status_code == 404


def test_delete_link_not_found(client):
    """Test deleting non-existent link."""
    response = client.delete('/api/links/nonexistent-id')
    assert response.status_code == 404
    data = response.get_json()
    assert data['status'] == 'error'


def test_list_links_after_create(client):
    """Test that created links appear in list."""
    # Create labels first
    client.post('/api/labels', json={
        'name': 'Person',
        'properties': [{'name': 'email', 'type': 'string'}],
        'relationships': []
    })
    client.post('/api/labels', json={
        'name': 'File',
        'properties': [{'name': 'path', 'type': 'string'}],
        'relationships': []
    })

    # Get initial count
    initial_response = client.get('/api/links')
    initial_count = len(initial_response.get_json()['links'])

    # Create multiple links
    created_ids = []
    for i in range(3):
        payload = {
            'name': f'Link {i}',
            'source_label': 'Person',
            'target_label': 'File',
            'match_strategy': 'property',
            'match_config': {'source_field': 'email', 'target_field': 'author'},
            'relationship_type': f'REL_{i}',
            'relationship_props': {}
        }
        resp = client.post('/api/links', json=payload)
        created_ids.append(resp.get_json()['link']['id'])

    # List all links
    response = client.get('/api/links')
    assert response.status_code == 200
    data = response.get_json()
    assert data['status'] == 'success'
    assert len(data['links']) == initial_count + 3

    # Verify our links are in the list
    link_names = [link['name'] for link in data['links']]
    for i in range(3):
        assert f'Link {i}' in link_names


def test_preview_link_requires_definition(client):
    """Test that preview requires a valid link definition."""
    response = client.post('/api/links/nonexistent-id/preview', json={'limit': 10})
    assert response.status_code == 404
    data = response.get_json()
    assert data['status'] == 'error'


def test_execute_link_requires_definition(client):
    """Test that execute requires a valid link definition."""
    response = client.post('/api/links/nonexistent-id/execute')
    assert response.status_code == 404
    data = response.get_json()
    assert data['status'] == 'error'


def test_list_jobs_empty(client):
    """Test listing jobs when none exist."""
    response = client.get('/api/links/jobs')
    assert response.status_code == 200
    data = response.get_json()
    assert data['status'] == 'success'
    assert 'jobs' in data
    assert isinstance(data['jobs'], list)


def test_get_job_status_not_found(client):
    """Test getting status of non-existent job."""
    response = client.get('/api/links/jobs/nonexistent-job-id')
    assert response.status_code == 404
    data = response.get_json()
    assert data['status'] == 'error'


# ===  Label→Label Refactor Tests ===


def test_create_link_with_labels(client):
    """Test creating a link with source_label and target_label (new model)."""
    # First, create labels
    client.post('/api/labels', json={
        'name': 'Person',
        'properties': [{'name': 'email', 'type': 'string'}],
        'relationships': []
    })
    client.post('/api/labels', json={
        'name': 'File',
        'properties': [{'name': 'path', 'type': 'string'}],
        'relationships': []
    })

    payload = {
        'name': 'Person to File',
        'source_label': 'Person',
        'target_label': 'File',
        'match_strategy': 'property',
        'match_config': {
            'source_field': 'email',
            'target_field': 'author_email'
        },
        'relationship_type': 'AUTHORED'
    }

    response = client.post('/api/links', json=payload)
    assert response.status_code == 200
    data = response.get_json()
    assert data['status'] == 'success'
    assert data['link']['source_label'] == 'Person'
    assert data['link']['target_label'] == 'File'
    assert data['link']['match_strategy'] == 'property'


def test_create_link_missing_source_label(client):
    """Test that source_label is required."""
    payload = {
        'name': 'Bad Link',
        'target_label': 'File',
        'match_strategy': 'property',
        'relationship_type': 'RELATED'
    }

    response = client.post('/api/links', json=payload)
    assert response.status_code == 400
    data = response.get_json()
    assert data['status'] == 'error'
    assert 'source_label' in data['error'].lower()


def test_create_link_missing_target_label(client):
    """Test that target_label is required."""
    payload = {
        'name': 'Bad Link',
        'source_label': 'Person',
        'match_strategy': 'property',
        'relationship_type': 'RELATED'
    }

    response = client.post('/api/links', json=payload)
    assert response.status_code == 400
    data = response.get_json()
    assert data['status'] == 'error'
    assert 'target_label' in data['error'].lower()


def test_create_link_nonexistent_label(client):
    """Test that labels must exist in registry."""
    payload = {
        'name': 'Bad Link',
        'source_label': 'NonexistentLabel',
        'target_label': 'AlsoDoesNotExist',
        'match_strategy': 'property',
        'relationship_type': 'RELATED'
    }

    response = client.post('/api/links', json=payload)
    assert response.status_code == 400
    data = response.get_json()
    assert data['status'] == 'error'


def test_create_link_fuzzy_match_strategy(client):
    """Test creating link with fuzzy match strategy."""
    # Create labels first
    client.post('/api/labels', json={
        'name': 'Author',
        'properties': [{'name': 'name', 'type': 'string'}],
        'relationships': []
    })
    client.post('/api/labels', json={
        'name': 'Document',
        'properties': [{'name': 'author_name', 'type': 'string'}],
        'relationships': []
    })

    payload = {
        'name': 'Author to Document (Fuzzy)',
        'source_label': 'Author',
        'target_label': 'Document',
        'match_strategy': 'fuzzy',
        'match_config': {
            'source_field': 'name',
            'target_field': 'author_name',
            'threshold': 85
        },
        'relationship_type': 'AUTHORED'
    }

    response = client.post('/api/links', json=payload)
    assert response.status_code == 200
    data = response.get_json()
    assert data['status'] == 'success'
    assert data['link']['match_strategy'] == 'fuzzy'


def test_create_link_table_import_strategy(client):
    """Test creating link with table_import match strategy."""
    # Create labels
    client.post('/api/labels', json={
        'name': 'Project',
        'properties': [{'name': 'name', 'type': 'string'}],
        'relationships': []
    })

    payload = {
        'name': 'Import Projects from CSV',
        'source_label': 'Project',
        'target_label': 'Project',
        'match_strategy': 'table_import',
        'match_config': {
            'table_data': 'name,budget\nProject A,100000\nProject B,200000'
        },
        'relationship_type': 'RELATED_TO'
    }

    response = client.post('/api/links', json=payload)
    assert response.status_code == 200
    data = response.get_json()
    assert data['status'] == 'success'
    assert data['link']['match_strategy'] == 'table_import'


def test_create_link_api_endpoint_strategy(client):
    """Test creating link with api_endpoint match strategy."""
    # Create labels
    client.post('/api/labels', json={
        'name': 'User',
        'properties': [{'name': 'id', 'type': 'number'}],
        'relationships': []
    })

    payload = {
        'name': 'Fetch Users from API',
        'source_label': 'User',
        'target_label': 'User',
        'match_strategy': 'api_endpoint',
        'match_config': {
            'url': 'https://api.example.com/users',
            'json_path': '$.data.users[*]'
        },
        'relationship_type': 'RELATED_TO'
    }

    response = client.post('/api/links', json=payload)
    assert response.status_code == 200
    data = response.get_json()
    assert data['status'] == 'success'
    assert data['link']['match_strategy'] == 'api_endpoint'


def test_get_available_labels(client):
    """Test getting available labels for dropdown population."""
    # Create some labels
    client.post('/api/labels', json={
        'name': 'Person',
        'properties': [{'name': 'name', 'type': 'string'}],
        'relationships': []
    })
    client.post('/api/labels', json={
        'name': 'File',
        'properties': [{'name': 'path', 'type': 'string'}],
        'relationships': []
    })

    response = client.get('/api/links/available-labels')
    assert response.status_code == 200
    data = response.get_json()
    assert data['status'] == 'success'
    assert 'labels' in data
    assert len(data['labels']) >= 2
    label_names = [l['name'] for l in data['labels']]
    assert 'Person' in label_names
    assert 'File' in label_names
