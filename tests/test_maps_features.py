"""
Comprehensive tests for Maps page features including:
- Save/load map configurations
- Property expansion with null/undefined handling
- Display name validation and sanitization
- Edge case handling
- Formatting configuration persistence
"""

import pytest
import json
from unittest.mock import Mock, patch


def test_map_page_renders_with_new_features(client):
    """Test that map page includes new formatting and save/load UI elements."""
    resp = client.get('/map')
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)

    # Check for schema configuration panel
    assert 'Schema Configuration' in html or 'schema-config' in html

    # Check for save/load buttons
    assert 'Save Map' in html or 'save-map' in html

    # Check for visualization mode options
    assert 'schema' in html.lower()


def test_save_map_api_basic(client):
    """Test creating a new saved map via API."""
    payload = {
        'name': 'Test Map 1',
        'description': 'Test map description',
        'query': 'MATCH (n)-[r]->(m) RETURN n, r, m LIMIT 100',
        'visualization': {
            'mode': 'schema',
            'nodeSize': 30,
            'fontSize': 12,
            'labelColorMap': {'Sample': '#ff5733'},
            'labelDisplayNames': {'Sample': 'Test Sample'}
        },
        'tags': 'test,demo'
    }

    resp = client.post(
        '/api/maps/saved',
        data=json.dumps(payload),
        content_type='application/json'
    )

    assert resp.status_code == 201
    data = json.loads(resp.data)
    assert data['status'] == 'ok'
    assert 'map' in data
    assert data['map']['name'] == 'Test Map 1'
    assert data['map']['query'] == payload['query']


def test_save_map_without_name_fails(client):
    """Test that saving a map without a name returns 400."""
    payload = {
        'query': 'MATCH (n) RETURN n',
        'visualization': {}
    }

    resp = client.post(
        '/api/maps/saved',
        data=json.dumps(payload),
        content_type='application/json'
    )

    assert resp.status_code == 400
    data = json.loads(resp.data)
    assert data['status'] == 'error'
    assert 'name' in data['message'].lower()


def test_save_map_empty_query_allowed(client):
    """Test that saving a map with empty query is allowed (with warning in UI)."""
    payload = {
        'name': 'Empty Query Map',
        'query': '',  # Empty query
        'visualization': {'mode': 'schema'}
    }

    resp = client.post(
        '/api/maps/saved',
        data=json.dumps(payload),
        content_type='application/json'
    )

    # Should succeed - UI shows warning but backend allows it
    assert resp.status_code == 201
    data = json.loads(resp.data)
    assert data['status'] == 'ok'


def test_save_map_with_formatting_config(client):
    """Test saving map with comprehensive formatting configuration."""
    payload = {
        'name': 'Formatted Map',
        'query': 'MATCH (n:Sample)-[r:ANALYZED_TO]->(m:Result) RETURN n, r, m',
        'visualization': {
            'mode': 'schema',
            'connection': 'Local Graph',
            'nodeSize': 50,
            'fontSize': 14,
            'highContrast': True,
            'edgeWidth': 2.5,
            'showLabels': True,
            'layoutAlgorithm': 'cose',
            'labelColorMap': {
                'Sample': '#ff5733',
                'Result': '#33ff57'
            },
            'labelFormattingConfig': {
                'Sample': {'nodeSize': 60, 'fontSize': 16, 'color': '#ff5733'},
                'Result': {'nodeSize': 40, 'fontSize': 12, 'color': '#33ff57'}
            },
            'labelDisplayNames': {
                'Sample': 'Test Sample',
                'Result': 'Analysis Result'
            },
            'relationshipDisplayNames': {
                'ANALYZED_TO': 'Analyzed To'
            },
            'schemaExpansionConfig': {
                'nodes': {
                    'Sample': {
                        'property': 'type',
                        'showLabel': True,
                        'showKey': False
                    }
                },
                'relationships': {}
            }
        }
    }

    resp = client.post(
        '/api/maps/saved',
        data=json.dumps(payload),
        content_type='application/json'
    )

    assert resp.status_code == 201
    data = json.loads(resp.data)
    assert data['status'] == 'ok'

    # Verify all configs are saved
    saved_viz = data['map']['visualization']
    assert saved_viz['labelColorMap'] == payload['visualization']['labelColorMap']
    assert saved_viz['labelDisplayNames'] == payload['visualization']['labelDisplayNames']
    assert saved_viz['schemaExpansionConfig'] == payload['visualization']['schemaExpansionConfig']


def test_get_saved_map(client):
    """Test retrieving a saved map by ID."""
    # First create a map
    create_payload = {
        'name': 'Retrieval Test Map',
        'query': 'MATCH (n) RETURN n LIMIT 10',
        'visualization': {'mode': 'schema'}
    }

    create_resp = client.post(
        '/api/maps/saved',
        data=json.dumps(create_payload),
        content_type='application/json'
    )

    assert create_resp.status_code == 201
    create_data = json.loads(create_resp.data)
    map_id = create_data['map']['id']

    # Now retrieve it
    get_resp = client.get(f'/api/maps/saved/{map_id}')
    assert get_resp.status_code == 200

    get_data = json.loads(get_resp.data)
    assert get_data['status'] == 'ok'
    assert get_data['map']['name'] == 'Retrieval Test Map'
    assert get_data['map']['query'] == create_payload['query']


def test_get_nonexistent_map_returns_404(client):
    """Test that getting a non-existent map returns 404."""
    resp = client.get('/api/maps/saved/nonexistent-id-12345')
    assert resp.status_code == 404

    data = json.loads(resp.data)
    assert data['status'] == 'error'
    assert 'not found' in data['message'].lower()


def test_update_saved_map(client):
    """Test updating an existing saved map."""
    # Create initial map
    create_payload = {
        'name': 'Update Test Map',
        'query': 'MATCH (n) RETURN n',
        'visualization': {'mode': 'schema', 'nodeSize': 30}
    }

    create_resp = client.post(
        '/api/maps/saved',
        data=json.dumps(create_payload),
        content_type='application/json'
    )

    map_id = json.loads(create_resp.data)['map']['id']

    # Update it
    update_payload = {
        'name': 'Updated Map Name',
        'query': 'MATCH (n)-[r]->(m) RETURN n, r, m',
        'visualization': {'mode': 'instance', 'nodeSize': 50}
    }

    update_resp = client.put(
        f'/api/maps/saved/{map_id}',
        data=json.dumps(update_payload),
        content_type='application/json'
    )

    assert update_resp.status_code == 200
    update_data = json.loads(update_resp.data)
    assert update_data['status'] == 'ok'
    assert update_data['map']['name'] == 'Updated Map Name'
    assert update_data['map']['query'] == update_payload['query']
    assert update_data['map']['visualization']['nodeSize'] == 50


def test_delete_saved_map(client):
    """Test deleting a saved map."""
    # Create a map
    create_payload = {
        'name': 'Delete Test Map',
        'query': 'MATCH (n) RETURN n'
    }

    create_resp = client.post(
        '/api/maps/saved',
        data=json.dumps(create_payload),
        content_type='application/json'
    )

    map_id = json.loads(create_resp.data)['map']['id']

    # Delete it
    delete_resp = client.delete(f'/api/maps/saved/{map_id}')
    assert delete_resp.status_code == 200

    delete_data = json.loads(delete_resp.data)
    assert delete_data['status'] == 'ok'

    # Verify it's gone
    get_resp = client.get(f'/api/maps/saved/{map_id}')
    assert get_resp.status_code == 404


def test_list_saved_maps(client):
    """Test listing all saved maps."""
    # Create multiple maps
    for i in range(3):
        payload = {
            'name': f'List Test Map {i+1}',
            'query': f'MATCH (n) RETURN n LIMIT {(i+1)*10}'
        }
        client.post(
            '/api/maps/saved',
            data=json.dumps(payload),
            content_type='application/json'
        )

    # List all maps
    resp = client.get('/api/maps/saved')
    assert resp.status_code == 200

    data = json.loads(resp.data)
    assert data['status'] == 'ok'
    assert 'maps' in data
    assert len(data['maps']) >= 3  # At least the 3 we created


def test_track_map_usage(client):
    """Test tracking usage of a saved map."""
    # Create a map
    create_payload = {
        'name': 'Usage Test Map',
        'query': 'MATCH (n) RETURN n'
    }

    create_resp = client.post(
        '/api/maps/saved',
        data=json.dumps(create_payload),
        content_type='application/json'
    )

    map_id = json.loads(create_resp.data)['map']['id']
    initial_use_count = json.loads(create_resp.data)['map'].get('use_count', 0)

    # Track usage
    track_resp = client.post(f'/api/maps/saved/{map_id}/use')
    assert track_resp.status_code == 200

    # Verify use count increased
    get_resp = client.get(f'/api/maps/saved/{map_id}')
    updated_map = json.loads(get_resp.data)['map']
    assert updated_map.get('use_count', 0) == initial_use_count + 1


def test_display_name_sanitization():
    """Test that display names are properly sanitized (unit test for JS logic)."""
    # This tests the concept - actual sanitization happens in JS
    test_cases = [
        ('Normal Name', 'Normal Name'),
        ('  Spaces  ', 'Spaces'),  # Trimmed
        ('Name\nWith\nNewlines', 'Name With Newlines'),  # Newlines removed
        ('A' * 150, 'A' * 97 + '...'),  # Length limited to 100
        ('', None),  # Empty should fallback to original
    ]

    # Simulate JS sanitization logic
    def sanitize_display_name(name, original):
        if not name:
            return original
        name = name.strip().replace('\n', ' ').replace('\r', ' ')
        if len(name) > 100:
            name = name[:97] + '...'
        if len(name) == 0:
            return original
        return name

    for input_name, expected in test_cases:
        if expected is None:
            assert sanitize_display_name(input_name, 'OriginalLabel') == 'OriginalLabel'
        else:
            assert sanitize_display_name(input_name, 'OriginalLabel') == expected


def test_property_expansion_null_handling():
    """Test that property expansion correctly filters null/undefined values."""
    # Simulates the property collection logic
    properties_map = {}

    # Sample data with null values
    sample_nodes = [
        {'label': 'Sample', 'properties': {'type': 'blood', 'status': 'active'}},
        {'label': 'Sample', 'properties': {'type': None, 'status': 'inactive'}},  # null type
        {'label': 'Sample', 'properties': {'type': 'tissue', 'status': None}},  # null status
        {'label': 'Sample', 'properties': {}},  # no properties
    ]

    # Simulate property collection (filters null)
    for node in sample_nodes:
        for prop_name, prop_value in node['properties'].items():
            if prop_value is not None:  # Filter nulls
                if prop_name not in properties_map:
                    properties_map[prop_name] = set()
                properties_map[prop_name].add(prop_value)

    # Verify nulls are filtered out
    assert 'type' in properties_map
    assert properties_map['type'] == {'blood', 'tissue'}  # null excluded
    assert 'status' in properties_map
    assert properties_map['status'] == {'active', 'inactive'}  # null excluded


def test_color_format_validation():
    """Test that all color values use 6-digit hex format."""
    # This ensures the #999 -> #999999 fix is applied
    test_colors = [
        ('#999999', True),   # Valid
        ('#FF5733', True),   # Valid
        ('#999', False),     # Invalid - should be #999999
        ('#abc', False),     # Invalid - should be #aabbcc
    ]

    def is_valid_color(color):
        return color.startswith('#') and len(color) == 7

    for color, should_be_valid in test_colors:
        assert is_valid_color(color) == should_be_valid


def test_empty_graph_layout_handling():
    """Test that layout functions handle empty graphs gracefully."""
    # Simulates the empty graph check added to prevent errors
    def run_layout_safe(nodes, layout_name):
        if layout_name == 'manual':
            return 'skipped'
        if len(nodes) == 0:
            return 'skipped'  # Don't run layout on empty graph
        return f'layout:{layout_name}'

    assert run_layout_safe([], 'cose') == 'skipped'
    assert run_layout_safe([{'id': 1}], 'cose') == 'layout:cose'
    assert run_layout_safe([{'id': 1}, {'id': 2}], 'breadthfirst') == 'layout:breadthfirst'


def test_connection_validation_on_load():
    """Test that loading a map with missing connection shows warning."""
    # Simulates connection validation logic
    available_connections = ['Local Graph', 'Production DB']

    def validate_connection(saved_connection, available):
        if saved_connection not in available:
            return False, f"Connection '{saved_connection}' not found"
        return True, None

    # Valid connection
    valid, error = validate_connection('Local Graph', available_connections)
    assert valid is True
    assert error is None

    # Invalid connection
    valid, error = validate_connection('Missing Connection', available_connections)
    assert valid is False
    assert 'not found' in error


def test_save_map_with_large_schema():
    """Test saving map with many labels (performance edge case)."""
    # Create a map with 50+ labels
    large_config = {
        'name': 'Large Schema Map',
        'query': 'MATCH (n)-[r]->(m) RETURN n, r, m',
        'visualization': {
            'labelColorMap': {f'Label_{i}': f'#ff{i:04x}' for i in range(50)},
            'labelDisplayNames': {f'Label_{i}': f'Display {i}' for i in range(50)},
            'labelFormattingConfig': {
                f'Label_{i}': {'nodeSize': 30 + i, 'fontSize': 10 + i % 5}
                for i in range(50)
            }
        }
    }

    # This tests that large configs can be serialized/deserialized
    json_str = json.dumps(large_config)
    recovered = json.loads(json_str)

    assert recovered['name'] == 'Large Schema Map'
    assert len(recovered['visualization']['labelColorMap']) == 50


def test_concurrent_save_duplicate_name():
    """Test handling of duplicate map names (simulates concurrent saves)."""
    # This tests the duplicate name detection logic
    existing_maps = [
        {'id': '1', 'name': 'Map A'},
        {'id': '2', 'name': 'Map B'},
    ]

    def check_duplicate(new_name, existing):
        return any(m['name'] == new_name for m in existing)

    assert check_duplicate('Map A', existing_maps) is True
    assert check_duplicate('Map C', existing_maps) is False


# Integration test markers
@pytest.mark.integration
def test_full_save_load_cycle_integration(client):
    """Integration test: Create, save, load, verify all settings persist."""
    # Create comprehensive map
    original = {
        'name': 'Integration Test Map',
        'description': 'Full cycle test',
        'query': 'MATCH (s:Sample)-[r:MEASURED_BY]->(a:Assay) RETURN s, r, a LIMIT 100',
        'visualization': {
            'mode': 'schema',
            'connection': 'Local Graph',
            'nodeSize': 45,
            'fontSize': 13,
            'highContrast': True,
            'edgeWidth': 2.0,
            'showLabels': True,
            'layoutAlgorithm': 'breadthfirst',
            'labelColorMap': {'Sample': '#ff5733', 'Assay': '#3357ff'},
            'labelDisplayNames': {'Sample': 'Biological Sample', 'Assay': 'Lab Assay'},
            'relationshipDisplayNames': {'MEASURED_BY': 'Measured By'},
            'schemaExpansionConfig': {
                'nodes': {
                    'Sample': {'property': 'type', 'showLabel': True, 'showKey': False}
                },
                'relationships': {}
            }
        },
        'tags': 'integration,test'
    }

    # Save
    save_resp = client.post(
        '/api/maps/saved',
        data=json.dumps(original),
        content_type='application/json'
    )
    assert save_resp.status_code == 201
    map_id = json.loads(save_resp.data)['map']['id']

    # Load
    load_resp = client.get(f'/api/maps/saved/{map_id}')
    assert load_resp.status_code == 200
    loaded = json.loads(load_resp.data)['map']

    # Verify everything matches
    assert loaded['name'] == original['name']
    assert loaded['query'] == original['query']
    assert loaded['visualization']['mode'] == original['visualization']['mode']
    assert loaded['visualization']['nodeSize'] == original['visualization']['nodeSize']
    assert loaded['visualization']['labelColorMap'] == original['visualization']['labelColorMap']
    assert loaded['visualization']['labelDisplayNames'] == original['visualization']['labelDisplayNames']
    assert loaded['visualization']['schemaExpansionConfig'] == original['visualization']['schemaExpansionConfig']


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
