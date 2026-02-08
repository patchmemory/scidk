"""Tests for label instance count API endpoint."""

import pytest


def test_instance_count_endpoint_exists(client):
    """Test that the instance count endpoint exists."""
    # Create a test label first
    label_data = {
        'name': 'TestLabel',
        'properties': [
            {'name': 'id', 'type': 'string', 'required': True, 'indexed': True}
        ],
        'relationships': []
    }

    # Save the label
    response = client.post('/api/labels', json=label_data)
    assert response.status_code == 200

    # Try to get instance count (will fail if Neo4j not configured, but endpoint should exist)
    response = client.get('/api/labels/TestLabel/instance-count')
    assert response.status_code in [200, 500]  # 200 if connected, 500 if Neo4j not configured

    # Check response structure
    data = response.get_json()
    assert 'status' in data
    assert data['status'] in ['success', 'error']

    if data['status'] == 'success':
        assert 'count' in data
        assert isinstance(data['count'], int)
    else:
        assert 'error' in data


def test_instance_count_label_not_found(client):
    """Test instance count for non-existent label returns 404."""
    response = client.get('/api/labels/NonExistentLabel/instance-count')
    assert response.status_code == 404

    data = response.get_json()
    assert data['status'] == 'error'
    assert 'not found' in data['error'].lower()


def test_instance_count_neo4j_not_configured(client):
    """Test instance count when Neo4j is not configured."""
    # Create a test label
    label_data = {
        'name': 'TestLabel2',
        'properties': [
            {'name': 'name', 'type': 'string'}
        ]
    }

    response = client.post('/api/labels', json=label_data)
    assert response.status_code == 200

    # Get instance count
    response = client.get('/api/labels/TestLabel2/instance-count')

    # Should handle gracefully (either success with 0 or error about Neo4j)
    assert response.status_code in [200, 500]

    data = response.get_json()
    assert 'status' in data

    if data['status'] == 'error':
        # Error message should mention Neo4j, configuration, or driver issues
        assert 'error' in data
        error_msg = data['error'].lower()
        assert 'neo4j' in error_msg or 'config' in error_msg or 'connect' in error_msg or 'driver' in error_msg
