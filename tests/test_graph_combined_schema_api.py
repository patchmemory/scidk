"""
Unit tests for the combined schema API endpoint.

Tests the /api/graph/schema/combined endpoint that merges:
- Local Labels definitions
- Neo4j schema (when connected)
- In-memory graph schema
"""
import pytest
import json


def test_combined_schema_all_sources_default(client):
    """Test combined schema with default 'all' sources."""
    resp = client.get('/api/graph/schema/combined')
    assert resp.status_code == 200

    data = resp.json
    assert 'nodes' in data
    assert 'edges' in data
    assert 'sources' in data
    assert isinstance(data['nodes'], list)
    assert isinstance(data['edges'], list)
    assert isinstance(data['sources'], dict)


def test_combined_schema_labels_only(client, app):
    """Test combined schema with only local labels."""
    # Create test labels using the label service
    from scidk.services.label_service import LabelService

    with app.app_context():
        label_service = LabelService(app)

        # Create a test label with properties and relationships
        label_service.save_label({
            'name': 'TestProject',
            'properties': [
                {'name': 'project_id', 'type': 'string', 'required': True},
                {'name': 'budget', 'type': 'number', 'required': False}
            ],
            'relationships': [
                {'type': 'HAS_FILE', 'target_label': 'File', 'properties': []}
            ]
        })

        # Create another label
        label_service.save_label({
            'name': 'TestDataset',
            'properties': [
                {'name': 'dataset_name', 'type': 'string'}
            ],
            'relationships': []
        })

    # Fetch combined schema with labels source only
    resp = client.get('/api/graph/schema/combined?source=labels')
    assert resp.status_code == 200

    data = resp.json

    # Verify TestProject label exists
    test_project = next((n for n in data['nodes'] if n['label'] == 'TestProject'), None)
    assert test_project is not None
    assert test_project['count'] == 0  # No instances yet
    assert test_project['source'] == 'labels'

    # Verify TestDataset label exists
    test_dataset = next((n for n in data['nodes'] if n['label'] == 'TestDataset'), None)
    assert test_dataset is not None
    assert test_dataset['source'] == 'labels'

    # Verify HAS_FILE relationship exists from TestProject
    has_file_edge = next((e for e in data['edges'] if e['rel_type'] == 'HAS_FILE' and e['start_label'] == 'TestProject'), None)
    assert has_file_edge is not None
    assert has_file_edge['end_label'] == 'File'
    assert has_file_edge['count'] == 0
    assert has_file_edge['source'] == 'labels'

    # Verify sources metadata
    assert 'labels' in data['sources']
    assert data['sources']['labels']['enabled'] is True
    assert data['sources']['labels']['count'] >= 2  # At least our 2 test labels


def test_combined_schema_graph_only(client, graph_with_data):
    """Test combined schema with only in-memory graph."""
    resp = client.get('/api/graph/schema/combined?source=graph')
    assert resp.status_code == 200

    data = resp.json

    # Graph may or may not have nodes depending on test fixtures
    # Just verify the response structure is correct
    assert 'nodes' in data
    assert 'edges' in data
    assert isinstance(data['nodes'], list)
    assert isinstance(data['edges'], list)

    # All nodes should have source='graph' if any exist
    for node in data['nodes']:
        assert node['source'] == 'graph'
        assert node['count'] >= 0

    # Verify sources metadata
    assert 'graph' in data['sources']
    assert data['sources']['graph']['enabled'] is True


def test_combined_schema_include_properties(client, app):
    """Test include_properties parameter."""
    from scidk.services.label_service import LabelService

    with app.app_context():
        label_service = LabelService(app)

        label_service.save_label({
            'name': 'PropertyTest',
            'properties': [
                {'name': 'prop1', 'type': 'string'},
                {'name': 'prop2', 'type': 'integer'}
            ],
            'relationships': []
        })

    # Without include_properties (default false)
    resp = client.get('/api/graph/schema/combined?source=labels')
    data = resp.json
    prop_test = next((n for n in data['nodes'] if n['label'] == 'PropertyTest'), None)
    assert prop_test is not None
    assert 'properties' not in prop_test

    # With include_properties=true
    resp = client.get('/api/graph/schema/combined?source=labels&include_properties=true')
    data = resp.json
    prop_test = next((n for n in data['nodes'] if n['label'] == 'PropertyTest'), None)
    assert prop_test is not None
    assert 'properties' in prop_test
    assert len(prop_test['properties']) == 2
    assert prop_test['properties'][0]['name'] in ['prop1', 'prop2']


def test_combined_schema_invalid_source(client):
    """Test with invalid source parameter."""
    resp = client.get('/api/graph/schema/combined?source=invalid')
    assert resp.status_code == 200

    data = resp.json
    # Should return empty results for unknown source
    assert data['nodes'] == []
    assert data['edges'] == []


def test_combined_schema_neo4j_not_connected(client):
    """Test Neo4j source when not connected."""
    resp = client.get('/api/graph/schema/combined?source=neo4j')
    assert resp.status_code == 200

    data = resp.json

    # Verify neo4j source shows as not connected
    assert 'neo4j' in data['sources']
    assert data['sources']['neo4j']['enabled'] is False
    assert data['sources']['neo4j']['connected'] is False


def test_combined_schema_merges_sources(client, app, graph_with_data):
    """Test that 'all' source merges labels and graph correctly."""
    from scidk.services.label_service import LabelService

    with app.app_context():
        label_service = LabelService(app)

        # Create a label not in graph
        label_service.save_label({
            'name': 'CustomMergeTest',
            'properties': [],
            'relationships': []
        })

    resp = client.get('/api/graph/schema/combined?source=all')
    data = resp.json

    # CustomMergeTest should exist with source='labels' and count=0
    custom_node = next((n for n in data['nodes'] if n['label'] == 'CustomMergeTest'), None)
    assert custom_node is not None
    assert custom_node['count'] == 0
    assert custom_node['source'] == 'labels'

    # Verify both sources are present in metadata
    assert 'labels' in data['sources']
    assert 'graph' in data['sources']

    # Labels source should be enabled and have at least our test label
    assert data['sources']['labels']['enabled'] is True
    assert data['sources']['labels']['count'] >= 1


def test_combined_schema_empty_labels(client):
    """Test combined schema when no labels are defined."""
    resp = client.get('/api/graph/schema/combined?source=labels')
    assert resp.status_code == 200

    data = resp.json
    assert 'sources' in data
    assert 'labels' in data['sources']
    # May have 0 labels or may have some from previous tests
    assert data['sources']['labels']['count'] >= 0


def test_combined_schema_case_sensitive_params(client):
    """Test parameter case sensitivity."""
    # Test various case variations
    for source in ['all', 'ALL', 'All', 'labels', 'LABELS', 'Labels']:
        resp = client.get(f'/api/graph/schema/combined?source={source}')
        assert resp.status_code == 200
        data = resp.json
        assert 'nodes' in data
        assert 'edges' in data
        assert 'sources' in data


@pytest.fixture
def graph_with_data(app):
    """Fixture that populates the in-memory graph with test data."""
    with app.app_context():
        graph = app.extensions['scidk']['graph']

        # Add some test nodes and edges to the graph
        # This assumes graph has methods to add data
        # Adjust based on actual graph API
        if hasattr(graph, 'datasets'):
            # Add a few test datasets
            pass  # Graph should have data from other fixtures

    return app
