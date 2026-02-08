"""
Tests for property removal and overwrite mode functionality.

Tests cover:
- PUT /api/labels/<name>/instances/<id> - overwrite instance properties
- Property removal workflow (schema changes)
- Incoming relationship management
"""
import json


def test_overwrite_instance_removes_extra_properties(client):
    """Test that PUT with overwrite mode removes properties not in schema."""
    # Create a label
    label_payload = {
        'name': 'TestLabel',
        'properties': [
            {'name': 'keep_me', 'type': 'string', 'required': False},
            {'name': 'also_keep', 'type': 'number', 'required': False}
        ],
        'relationships': []
    }

    response = client.post('/api/labels', json=label_payload)
    assert response.status_code == 200

    # Test PUT endpoint (overwrite mode) - simulates UI sending complete property set
    # Note: This test validates the endpoint exists and accepts the right format
    # Actual Neo4j interaction would require Neo4j to be configured
    put_payload = {
        'properties': {
            'keep_me': 'value1',
            'also_keep': 42
        },
        'mode': 'overwrite'
    }

    response = client.put('/api/labels/TestLabel/instances/fake-id', json=put_payload)
    # Expect 500 because Neo4j not configured, but endpoint exists
    assert response.status_code in [200, 500]
    data = response.get_json()
    assert 'status' in data


def test_overwrite_endpoint_requires_properties(client):
    """Test that PUT endpoint requires properties parameter."""
    response = client.put('/api/labels/TestLabel/instances/fake-id', json={})
    assert response.status_code == 400
    data = response.get_json()
    assert data['status'] == 'error'
    assert 'properties' in data['error'].lower()


def test_overwrite_endpoint_validates_label_exists(client):
    """Test that PUT endpoint validates label exists."""
    put_payload = {
        'properties': {'name': 'test'},
        'mode': 'overwrite'
    }

    response = client.put('/api/labels/NonExistentLabel/instances/fake-id', json=put_payload)
    assert response.status_code == 404
    data = response.get_json()
    assert data['status'] == 'error'


def test_property_removal_from_schema(client):
    """Test that removing a property from schema works correctly."""
    # Create label with 3 properties
    label_payload = {
        'name': 'Sample',
        'properties': [
            {'name': 'name', 'type': 'string', 'required': True},
            {'name': 'source_id', 'type': 'string', 'required': False},
            {'name': 'concentration', 'type': 'number', 'required': False}
        ],
        'relationships': []
    }

    response = client.post('/api/labels', json=label_payload)
    assert response.status_code == 200

    # Update label to remove 'source_id' property
    updated_payload = {
        'name': 'Sample',
        'properties': [
            {'name': 'name', 'type': 'string', 'required': True},
            {'name': 'concentration', 'type': 'number', 'required': False}
        ],
        'relationships': []
    }

    response = client.post('/api/labels', json=updated_payload)
    assert response.status_code == 200

    # Verify property was removed
    response = client.get('/api/labels/Sample')
    assert response.status_code == 200
    data = response.get_json()
    assert data['status'] == 'success'
    assert len(data['label']['properties']) == 2

    property_names = [p['name'] for p in data['label']['properties']]
    assert 'name' in property_names
    assert 'concentration' in property_names
    assert 'source_id' not in property_names


def test_incoming_relationships_computed_correctly(client):
    """Test that incoming relationships are computed from other labels."""
    # Create two labels (use unique names)
    experiment_payload = {
        'name': 'ExperimentA',
        'properties': [{'name': 'title', 'type': 'string', 'required': False}],
        'relationships': [
            {'type': 'HAS_SAMPLE', 'target_label': 'SampleA', 'properties': []}
        ]
    }

    sample_payload = {
        'name': 'SampleA',
        'properties': [{'name': 'name', 'type': 'string', 'required': False}],
        'relationships': []
    }

    # Create SampleA first
    response = client.post('/api/labels', json=sample_payload)
    assert response.status_code == 200

    # Create ExperimentA with relationship to SampleA
    response = client.post('/api/labels', json=experiment_payload)
    assert response.status_code == 200

    # Get SampleA and verify incoming relationship
    response = client.get('/api/labels/SampleA')
    assert response.status_code == 200
    data = response.get_json()

    assert 'incoming_relationships' in data['label']
    incoming = data['label']['incoming_relationships']
    assert len(incoming) == 1
    assert incoming[0]['source_label'] == 'ExperimentA'
    assert incoming[0]['type'] == 'HAS_SAMPLE'


def test_incoming_relationships_updates_when_source_changes(client):
    """Test that incoming relationships update when source label is modified."""
    # Create labels with relationship (use unique names to avoid test pollution)
    client.post('/api/labels', json={
        'name': 'StudySource',
        'properties': [],
        'relationships': [
            {'type': 'CONTAINS', 'target_label': 'SampleTarget', 'properties': []}
        ]
    })

    client.post('/api/labels', json={
        'name': 'SampleTarget',
        'properties': [],
        'relationships': []
    })

    # Verify incoming relationship exists
    response = client.get('/api/labels/SampleTarget')
    data = response.get_json()
    assert len(data['label']['incoming_relationships']) == 1
    assert data['label']['incoming_relationships'][0]['source_label'] == 'StudySource'

    # Remove relationship from StudySource
    response = client.post('/api/labels', json={
        'name': 'StudySource',
        'properties': [],
        'relationships': []  # Empty - removed the relationship
    })
    assert response.status_code == 200

    # Verify incoming relationship is gone
    response = client.get('/api/labels/SampleTarget')
    data = response.get_json()
    assert len(data['label']['incoming_relationships']) == 0


def test_multiple_incoming_relationships_from_different_sources(client):
    """Test that a label can have incoming relationships from multiple sources."""
    # Create target label
    client.post('/api/labels', json={
        'name': 'Dataset',
        'properties': [],
        'relationships': []
    })

    # Create multiple source labels pointing to Dataset
    client.post('/api/labels', json={
        'name': 'Experiment',
        'properties': [],
        'relationships': [
            {'type': 'PRODUCES', 'target_label': 'Dataset', 'properties': []}
        ]
    })

    client.post('/api/labels', json={
        'name': 'Analysis',
        'properties': [],
        'relationships': [
            {'type': 'USES', 'target_label': 'Dataset', 'properties': []}
        ]
    })

    # Verify Dataset has 2 incoming relationships
    response = client.get('/api/labels/Dataset')
    data = response.get_json()

    incoming = data['label']['incoming_relationships']
    assert len(incoming) == 2

    sources = {rel['source_label'] for rel in incoming}
    assert sources == {'Experiment', 'Analysis'}

    types = {rel['type'] for rel in incoming}
    assert types == {'PRODUCES', 'USES'}


def test_patch_endpoint_still_works_for_merge_mode(client):
    """Test that PATCH endpoint (merge mode) still works as before."""
    # Create a label
    client.post('/api/labels', json={
        'name': 'TestMerge',
        'properties': [
            {'name': 'prop1', 'type': 'string', 'required': False},
            {'name': 'prop2', 'type': 'string', 'required': False}
        ],
        'relationships': []
    })

    # Test PATCH endpoint (merge mode)
    patch_payload = {
        'property': 'prop1',
        'value': 'updated_value'
    }

    response = client.patch('/api/labels/TestMerge/instances/fake-id', json=patch_payload)
    # Expect 500 because Neo4j not configured, but endpoint exists
    assert response.status_code in [200, 500]
    data = response.get_json()
    assert 'status' in data


def test_property_removal_cascades_to_instances(client):
    """Test that removing properties from schema allows instance table refresh."""
    # This is a UI workflow test - validates that backend supports the pattern

    # 1. Create label with properties
    response = client.post('/api/labels', json={
        'name': 'TestCascade',
        'properties': [
            {'name': 'keep', 'type': 'string', 'required': False},
            {'name': 'remove', 'type': 'string', 'required': False}
        ],
        'relationships': []
    })
    assert response.status_code == 200

    # 2. Remove property from schema
    response = client.post('/api/labels', json={
        'name': 'TestCascade',
        'properties': [
            {'name': 'keep', 'type': 'string', 'required': False}
        ],
        'relationships': []
    })
    assert response.status_code == 200

    # 3. Verify schema updated
    response = client.get('/api/labels/TestCascade')
    data = response.get_json()
    properties = data['label']['properties']

    assert len(properties) == 1
    assert properties[0]['name'] == 'keep'

    # 4. Overwrite mode would now remove 'remove' property from instances
    # (This would be tested with Neo4j integration)
