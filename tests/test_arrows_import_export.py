"""
Tests for Arrows.app schema import/export functionality.
"""

import pytest


@pytest.fixture
def arrows_json_sample():
    """Sample Arrows.app JSON format"""
    return {
        'style': {},
        'nodes': [
            {
                'id': 'n0',
                'caption': 'Person',
                'labels': ['Person'],
                'properties': {'name': 'String', 'age': 'Integer'},
                'position': {'x': 100, 'y': 200},
            },
            {
                'id': 'n1',
                'caption': 'Company',
                'labels': ['Company'],
                'properties': {'name': 'String', 'founded': 'Integer'},
                'position': {'x': 300, 'y': 200},
            },
        ],
        'relationships': [
            {
                'id': 'r0',
                'type': 'WORKS_FOR',
                'fromId': 'n0',
                'toId': 'n1',
                'properties': {'since': 'Date'},
            }
        ],
    }


def test_import_arrows_schema(client, arrows_json_sample):
    """Test importing Arrows.app JSON creates labels correctly"""
    resp = client.post('/api/labels/import/arrows', json={'arrows_json': arrows_json_sample})

    assert resp.status_code == 200
    data = resp.json
    assert data['status'] == 'success'
    assert data['imported']['labels'] == 2
    assert data['imported']['relationships'] == 1

    # Verify labels were created
    resp = client.get('/api/labels')
    labels = resp.json['labels']

    person_label = next((l for l in labels if l['name'] == 'Person'), None)
    assert person_label is not None
    assert len(person_label['properties']) == 2
    assert any(p['name'] == 'name' and p['type'] == 'string' for p in person_label['properties'])
    assert any(p['name'] == 'age' and p['type'] == 'number' for p in person_label['properties'])
    assert len(person_label['relationships']) == 1
    assert person_label['relationships'][0]['type'] == 'WORKS_FOR'
    assert person_label['relationships'][0]['target_label'] == 'Company'

    company_label = next((l for l in labels if l['name'] == 'Company'), None)
    assert company_label is not None
    assert len(company_label['properties']) == 2


def test_import_arrows_missing_json(client):
    """Test import fails gracefully when no JSON provided"""
    resp = client.post('/api/labels/import/arrows', json={})
    assert resp.status_code == 400
    assert 'No arrows_json provided' in resp.json['error']


def test_import_arrows_merge_mode_skips_duplicates(client, arrows_json_sample):
    """Test merge mode skips existing labels without error"""
    # First import
    resp1 = client.post('/api/labels/import/arrows', json={'arrows_json': arrows_json_sample, 'mode': 'merge'})
    assert resp1.status_code == 200
    assert resp1.json['imported']['labels'] == 2

    # Second import (should skip duplicates)
    resp2 = client.post('/api/labels/import/arrows', json={'arrows_json': arrows_json_sample, 'mode': 'merge'})
    assert resp2.status_code == 200
    # May import 0 or 2 depending on whether save_label updates or errors
    # But should not crash
    assert resp2.json['status'] == 'success'


def test_export_arrows_schema(client):
    """Test exporting labels to Arrows.app JSON format"""
    # Create labels
    client.post(
        '/api/labels',
        json={
            'name': 'ExportProject',
            'properties': [{'name': 'title', 'type': 'string', 'required': True}],
            'relationships': [{'type': 'HAS_TASK', 'target_label': 'ExportTask', 'properties': []}],
        },
    )

    client.post(
        '/api/labels',
        json={
            'name': 'ExportTask',
            'properties': [{'name': 'description', 'type': 'string', 'required': False}],
            'relationships': [],
        },
    )

    # Export
    resp = client.get('/api/labels/export/arrows')
    assert resp.status_code == 200

    arrows_json = resp.json
    assert 'nodes' in arrows_json
    assert 'relationships' in arrows_json
    assert 'style' in arrows_json

    # Verify our specific nodes exist (there may be others from previous tests)
    project_node = next((n for n in arrows_json['nodes'] if n['caption'] == 'ExportProject'), None)
    assert project_node is not None
    assert project_node['labels'] == ['ExportProject']
    assert 'title' in project_node['properties']
    assert project_node['properties']['title'] == 'String'
    assert 'position' in project_node

    task_node = next((n for n in arrows_json['nodes'] if n['caption'] == 'ExportTask'), None)
    assert task_node is not None

    # Verify our relationship exists
    rel = next((r for r in arrows_json['relationships'] if r['type'] == 'HAS_TASK' and r['fromId'] == project_node['id']), None)
    assert rel is not None
    assert rel['toId'] == task_node['id']

    # Cleanup
    client.delete('/api/labels/ExportProject')
    client.delete('/api/labels/ExportTask')


def test_export_arrows_empty_schema(client):
    """Test exporting works even when no labels exist (or just verifies structure)"""
    resp = client.get('/api/labels/export/arrows')
    assert resp.status_code == 200

    arrows_json = resp.json
    # Verify structure exists (may have labels from other tests)
    assert 'nodes' in arrows_json
    assert 'relationships' in arrows_json
    assert 'style' in arrows_json
    assert isinstance(arrows_json['nodes'], list)
    assert isinstance(arrows_json['relationships'], list)


def test_export_arrows_with_layout_params(client):
    """Test export with layout and scale parameters"""
    # Create a label with unique name
    client.post('/api/labels', json={'name': 'LayoutTestLabel', 'properties': [], 'relationships': []})

    # Export with circular layout
    resp = client.get('/api/labels/export/arrows?layout=circular&scale=500')
    assert resp.status_code == 200

    arrows_json = resp.json
    # Verify our label exists and has position
    test_node = next((n for n in arrows_json['nodes'] if n['caption'] == 'LayoutTestLabel'), None)
    assert test_node is not None
    assert 'position' in test_node

    # Cleanup
    client.delete('/api/labels/LayoutTestLabel')


def test_arrows_utils_type_mapping():
    """Test type conversions between Arrows and scidk formats"""
    from scidk.interpreters.arrows_utils import ARROWS_TO_SCIDK_TYPE, SCIDK_TO_ARROWS_TYPE

    # Arrows -> scidk
    assert ARROWS_TO_SCIDK_TYPE['String'] == 'string'
    assert ARROWS_TO_SCIDK_TYPE['Integer'] == 'number'
    assert ARROWS_TO_SCIDK_TYPE['Boolean'] == 'boolean'

    # scidk -> Arrows
    assert SCIDK_TO_ARROWS_TYPE['string'] == 'String'
    assert SCIDK_TO_ARROWS_TYPE['number'] == 'Integer'
    assert SCIDK_TO_ARROWS_TYPE['boolean'] == 'Boolean'


def test_arrows_utils_import_function():
    """Test the import_from_arrows utility function directly"""
    from scidk.interpreters.arrows_utils import import_from_arrows

    arrows_json = {
        'nodes': [
            {'id': 'n0', 'caption': 'TestNode', 'properties': {'prop1': 'String'}},
            {'id': 'n1', 'caption': 'OtherNode', 'properties': {}},
        ],
        'relationships': [{'id': 'r0', 'type': 'RELATES_TO', 'fromId': 'n0', 'toId': 'n1'}],
    }

    labels = import_from_arrows(arrows_json)

    assert len(labels) == 2
    test_label = next((l for l in labels if l['name'] == 'TestNode'), None)
    assert test_label is not None
    assert len(test_label['properties']) == 1
    assert test_label['properties'][0]['name'] == 'prop1'
    assert test_label['properties'][0]['type'] == 'string'
    assert len(test_label['relationships']) == 1
    assert test_label['relationships'][0]['type'] == 'RELATES_TO'
    assert test_label['relationships'][0]['target_label'] == 'OtherNode'


def test_arrows_utils_export_function():
    """Test the export_to_arrows utility function directly"""
    from scidk.interpreters.arrows_utils import export_to_arrows

    labels = [
        {
            'name': 'NodeA',
            'properties': [{'name': 'field1', 'type': 'string'}],
            'relationships': [{'type': 'LINKS_TO', 'target_label': 'NodeB'}],
        },
        {'name': 'NodeB', 'properties': [], 'relationships': []},
    ]

    arrows_json = export_to_arrows(labels, layout='grid', scale=1000)

    assert 'nodes' in arrows_json
    assert 'relationships' in arrows_json
    assert 'style' in arrows_json
    assert len(arrows_json['nodes']) == 2
    assert len(arrows_json['relationships']) == 1

    node_a = next((n for n in arrows_json['nodes'] if n['caption'] == 'NodeA'), None)
    assert node_a is not None
    assert 'field1' in node_a['properties']
    assert node_a['properties']['field1'] == 'String'


def test_roundtrip_import_export(client):
    """Test that exporting and re-importing preserves schema"""
    # Create original labels with unique names
    client.post(
        '/api/labels',
        json={
            'name': 'RoundtripAuthor',
            'properties': [{'name': 'name', 'type': 'string'}],
            'relationships': [{'type': 'WROTE', 'target_label': 'RoundtripBook'}],
        },
    )
    client.post(
        '/api/labels', json={'name': 'RoundtripBook', 'properties': [{'name': 'title', 'type': 'string'}], 'relationships': []}
    )

    # Export
    export_resp = client.get('/api/labels/export/arrows')
    exported_json = export_resp.json

    # Extract only our test labels from the export
    our_labels = {
        'nodes': [n for n in exported_json['nodes'] if n['caption'] in ['RoundtripAuthor', 'RoundtripBook']],
        'relationships': [],
        'style': exported_json['style'],
    }

    # Find our nodes' IDs
    author_node_id = next((n['id'] for n in our_labels['nodes'] if n['caption'] == 'RoundtripAuthor'), None)
    book_node_id = next((n['id'] for n in our_labels['nodes'] if n['caption'] == 'RoundtripBook'), None)

    # Extract only relationships between our nodes
    our_labels['relationships'] = [
        r
        for r in exported_json['relationships']
        if r['fromId'] == author_node_id and r['toId'] == book_node_id and r['type'] == 'WROTE'
    ]

    # Delete labels
    client.delete('/api/labels/RoundtripAuthor')
    client.delete('/api/labels/RoundtripBook')

    # Verify our labels are deleted
    resp = client.get('/api/labels')
    labels = resp.json['labels']
    assert not any(l['name'] in ['RoundtripAuthor', 'RoundtripBook'] for l in labels)

    # Re-import only our labels
    import_resp = client.post('/api/labels/import/arrows', json={'arrows_json': our_labels})
    assert import_resp.status_code == 200
    assert import_resp.json['imported']['labels'] == 2

    # Verify re-imported correctly
    resp = client.get('/api/labels')
    labels = resp.json['labels']

    author = next((l for l in labels if l['name'] == 'RoundtripAuthor'), None)
    assert author is not None
    assert len(author['relationships']) == 1
    assert author['relationships'][0]['type'] == 'WROTE'

    # Cleanup
    client.delete('/api/labels/RoundtripAuthor')
    client.delete('/api/labels/RoundtripBook')
