"""
Unit tests for EDA file interpreter.
"""
import json
import zipfile
import tempfile
from pathlib import Path
import pytest

from scidk.interpreters.eda_interpreter import parse_eda_file, eda_to_labels


def create_test_eda_file(data, filename='test.eda'):
    """Helper to create a test EDA file."""
    tmp = tempfile.NamedTemporaryFile(suffix='.eda', delete=False)
    with zipfile.ZipFile(tmp.name, 'w') as zf:
        zf.writestr('model', json.dumps(data))
    tmp.close()
    return tmp.name


def test_parse_eda_file_single_node():
    """Test parsing .eda file with single node."""
    eda_data = {
        'childShapes': [
            {
                'resourceId': 'n0',
                'stencil': {'id': 'Treatment'},
                'properties': {'name': 'Drug A', 'dose': '10mg'},
                'propertyTypes': {'name': 'String', 'dose': 'String'},
                'outgoing': [],
                'incoming': []
            }
        ]
    }

    tmp_path = create_test_eda_file(eda_data)
    try:
        nodes, edges = parse_eda_file(tmp_path)
        assert len(nodes) == 1
        assert len(edges) == 0
        assert nodes[0]['stencil']['id'] == 'Treatment'
        assert nodes[0]['properties']['name'] == 'Drug A'
    finally:
        Path(tmp_path).unlink()


def test_parse_eda_file_with_edges():
    """Test parsing .eda file with nodes and edges."""
    eda_data = {
        'childShapes': [
            {
                'resourceId': 'n0',
                'stencil': {'id': 'Treatment'},
                'properties': {'name': 'Drug A'},
                'propertyTypes': {'name': 'String'},
                'outgoing': [],
                'incoming': []
            },
            {
                'resourceId': 'n1',
                'stencil': {'id': 'Subject'},
                'properties': {'id': 'Mouse001'},
                'propertyTypes': {'id': 'String'},
                'outgoing': [],
                'incoming': []
            },
            {
                'resourceId': 'e0',
                'stencil': {'id': 'APPLIED_TO'},
                'target': {'resourceId': 'n1'},
                'properties': {'name': 'applies'},
                'propertyTypes': {},
                'outgoing': [{'resourceId': 'n1'}],
                'incoming': [{'resourceId': 'n0'}]
            }
        ]
    }

    tmp_path = create_test_eda_file(eda_data)
    try:
        nodes, edges = parse_eda_file(tmp_path)
        assert len(nodes) == 2
        assert len(edges) == 1
        assert edges[0]['stencil']['id'] == 'APPLIED_TO'
    finally:
        Path(tmp_path).unlink()


def test_parse_eda_file_not_found():
    """Test parsing nonexistent file raises FileNotFoundError."""
    with pytest.raises(FileNotFoundError):
        parse_eda_file('/nonexistent/file.eda')


def test_parse_eda_file_wrong_extension():
    """Test parsing file with wrong extension raises ValueError."""
    tmp = tempfile.NamedTemporaryFile(suffix='.txt', delete=False)
    tmp.close()
    try:
        with pytest.raises(ValueError, match='Not an EDA file'):
            parse_eda_file(tmp.name)
    finally:
        Path(tmp.name).unlink()


def test_eda_to_labels_basic():
    """Test converting EDA nodes to labels."""
    eda_nodes = [
        {
            'resourceId': 'n0',
            'stencil': {'id': 'Treatment'},
            'properties': {'name': 'Drug A', 'dose': '10mg'},
            'propertyTypes': {'name': 'String', 'dose': 'String'},
            'outgoing': [],
            'incoming': []
        }
    ]

    labels = eda_to_labels(eda_nodes)

    assert len(labels) == 1
    assert labels[0]['name'] == 'Treatment'
    assert len(labels[0]['properties']) == 2

    prop_names = [p['name'] for p in labels[0]['properties']]
    assert 'name' in prop_names
    assert 'dose' in prop_names

    # Check type mapping
    for prop in labels[0]['properties']:
        assert prop['type'] == 'string'
        assert prop['required'] == False


def test_eda_to_labels_type_mapping():
    """Test EDA to scidk type mapping."""
    eda_nodes = [
        {
            'resourceId': 'n0',
            'stencil': {'id': 'Measurement'},
            'properties': {
                'text': 'value',
                'count': 42,
                'weight': 3.14,
                'active': True,
                'date': '2024-01-01'
            },
            'propertyTypes': {
                'text': 'String',
                'count': 'Integer',
                'weight': 'Float',
                'active': 'Boolean',
                'date': 'Date'
            },
            'outgoing': [],
            'incoming': []
        }
    ]

    labels = eda_to_labels(eda_nodes)
    props = {p['name']: p['type'] for p in labels[0]['properties']}

    assert props['text'] == 'string'
    assert props['count'] == 'number'
    assert props['weight'] == 'number'
    assert props['active'] == 'boolean'
    assert props['date'] == 'date'


def test_eda_to_labels_with_relationships():
    """Test converting EDA nodes with relationships."""
    eda_nodes = [
        {
            'resourceId': 'n0',
            'stencil': {'id': 'Treatment'},
            'properties': {'name': 'Drug A'},
            'propertyTypes': {'name': 'String'},
            'outgoing': [{'target': 'n1'}],
            'incoming': []
        },
        {
            'resourceId': 'n1',
            'stencil': {'id': 'Subject'},
            'properties': {'id': 'Mouse001'},
            'propertyTypes': {'id': 'String'},
            'outgoing': [],
            'incoming': [{'target': 'n0'}]
        }
    ]

    labels = eda_to_labels(eda_nodes)

    assert len(labels) == 2

    treatment = next(l for l in labels if l['name'] == 'Treatment')
    assert len(treatment['relationships']) == 1
    assert treatment['relationships'][0]['type'] == 'APPLIED_TO'
    assert treatment['relationships'][0]['target_label'] == 'Subject'


def test_eda_to_labels_dedupe_properties():
    """Test that duplicate properties are merged."""
    eda_nodes = [
        {
            'resourceId': 'n0',
            'stencil': {'id': 'Subject'},
            'properties': {'id': 'M001', 'weight': 25},
            'propertyTypes': {'id': 'String', 'weight': 'Integer'},
            'outgoing': [],
            'incoming': []
        },
        {
            'resourceId': 'n1',
            'stencil': {'id': 'Subject'},
            'properties': {'id': 'M002', 'age': 8},
            'propertyTypes': {'id': 'String', 'age': 'Integer'},
            'outgoing': [],
            'incoming': []
        }
    ]

    labels = eda_to_labels(eda_nodes)

    # Should have only one Subject label
    assert len(labels) == 1
    assert labels[0]['name'] == 'Subject'

    # Should have properties from both nodes
    prop_names = [p['name'] for p in labels[0]['properties']]
    assert 'id' in prop_names
    assert 'weight' in prop_names
    assert 'age' in prop_names


def test_eda_to_labels_with_explicit_edges():
    """Test converting with explicit edge objects."""
    eda_nodes = [
        {
            'resourceId': 'n0',
            'stencil': {'id': 'Experiment'},
            'properties': {'name': 'Exp1'},
            'propertyTypes': {'name': 'String'},
            'outgoing': [],
            'incoming': []
        },
        {
            'resourceId': 'n1',
            'stencil': {'id': 'Subject'},
            'properties': {'id': 'M001'},
            'propertyTypes': {'id': 'String'},
            'outgoing': [],
            'incoming': []
        }
    ]

    eda_edges = [
        {
            'resourceId': 'e0',
            'stencil': {'id': 'INCLUDES'},
            'incoming': [{'resourceId': 'n0'}],
            'outgoing': [{'resourceId': 'n1'}],
            'properties': {},
            'propertyTypes': {}
        }
    ]

    labels = eda_to_labels(eda_nodes, eda_edges)

    experiment = next(l for l in labels if l['name'] == 'Experiment')
    assert len(experiment['relationships']) == 1
    assert experiment['relationships'][0]['type'] == 'INCLUDES'
    assert experiment['relationships'][0]['target_label'] == 'Subject'


def test_eda_to_labels_empty_input():
    """Test with empty input."""
    labels = eda_to_labels([])
    assert labels == []


def test_eda_to_labels_missing_stencil():
    """Test handling nodes with missing stencil."""
    eda_nodes = [
        {
            'resourceId': 'n0',
            'properties': {'name': 'value'},
            'propertyTypes': {'name': 'String'},
            'outgoing': [],
            'incoming': []
        }
    ]

    labels = eda_to_labels(eda_nodes)
    # Should skip nodes without stencil or create with default
    # Current implementation skips them
    assert len(labels) == 0 or labels[0]['name'] == 'Unknown'
