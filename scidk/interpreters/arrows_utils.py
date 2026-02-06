"""
Utilities for importing/exporting Neo4j Arrows.app JSON format.

Reference implementation: dev/code-imports/nc3rsEDA/nc3rsEDA/neo4jSchemaExport.py
"""

import math
from typing import Any, Dict, List, Tuple

# Type mapping dictionaries
ARROWS_TO_SCIDK_TYPE = {
    'String': 'string',
    'Integer': 'number',
    'Float': 'number',
    'Boolean': 'boolean',
    'Date': 'date',
    'DateTime': 'datetime',
}

SCIDK_TO_ARROWS_TYPE = {
    'string': 'String',
    'number': 'Integer',
    'boolean': 'Boolean',
    'date': 'Date',
    'datetime': 'DateTime',
}


def export_to_arrows(labels: List[Dict[str, Any]], layout: str = 'grid', scale: int = 1000) -> Dict[str, Any]:
    """
    Convert scidk labels to Arrows.app JSON format.

    Args:
        labels: List of label dicts from LabelService
        layout: 'grid', 'circular', or 'force' (default: 'grid')
        scale: Position scaling factor (default: 1000)

    Returns:
        dict: Arrows.app JSON format
    """
    nodes = []
    relationships = []
    node_id_map = {}

    # Generate positions based on layout
    positions = _generate_layout(len(labels), layout, scale)

    # Create nodes
    for i, label in enumerate(labels):
        node_id = f'n{i}'
        node_id_map[label['name']] = node_id

        properties = {
            prop['name']: SCIDK_TO_ARROWS_TYPE.get(prop['type'], 'String')
            for prop in label.get('properties', [])
        }

        nodes.append({
            'id': node_id,
            'position': positions[i],
            'caption': label['name'],
            'labels': [label['name']],
            'properties': properties,
            'style': {},
        })

    # Create relationships
    rel_id = 0
    for label in labels:
        from_id = node_id_map[label['name']]
        for rel in label.get('relationships', []):
            to_id = node_id_map.get(rel['target_label'])
            if not to_id:
                continue

            relationships.append({
                'id': f'r{rel_id}',
                'type': rel['type'],
                'fromId': from_id,
                'toId': to_id,
                'properties': {},
                'style': {},
            })
            rel_id += 1

    return {
        'style': _default_style(),
        'nodes': nodes,
        'relationships': relationships,
    }


def import_from_arrows(arrows_json: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Parse Arrows.app JSON to scidk label definitions.

    Args:
        arrows_json: dict from Arrows.app export

    Returns:
        list: Label definitions ready for LabelService.create_label()
    """
    labels = []
    node_map = {}

    # First pass: create labels
    for node in arrows_json.get('nodes', []):
        label_name = node.get('caption') or (node.get('labels', [''])[0] if node.get('labels') else '')
        if not label_name:
            continue

        node_map[node['id']] = label_name

        properties = [
            {'name': prop_name, 'type': ARROWS_TO_SCIDK_TYPE.get(prop_type, 'string'), 'required': False}
            for prop_name, prop_type in node.get('properties', {}).items()
        ]

        labels.append({'name': label_name, 'properties': properties, 'relationships': []})

    # Second pass: add relationships
    label_dict = {l['name']: l for l in labels}
    for rel in arrows_json.get('relationships', []):
        from_label = node_map.get(rel['fromId'])
        to_label = node_map.get(rel['toId'])

        if from_label and to_label and from_label in label_dict:
            label_dict[from_label]['relationships'].append(
                {'type': rel['type'], 'target_label': to_label, 'properties': []}
            )

    return labels


def _generate_layout(n: int, layout_type: str, scale: int) -> List[Dict[str, int]]:
    """Generate positions for n nodes using specified layout"""
    if layout_type == 'circular':
        return _circular_layout(n, scale)
    # Default to grid
    return _grid_layout(n, scale)


def _grid_layout(n: int, scale: int) -> List[Dict[str, int]]:
    """Simple grid layout"""
    cols = int(n**0.5) + 1
    positions = []
    for i in range(n):
        x = (i % cols) * (scale // 4)
        y = (i // cols) * (scale // 4)
        positions.append({'x': x, 'y': y})
    return positions


def _circular_layout(n: int, scale: int) -> List[Dict[str, int]]:
    """Circular layout"""
    positions = []
    radius = scale // 3
    for i in range(n):
        angle = 2 * math.pi * i / n if n > 0 else 0
        x = int(radius * math.cos(angle))
        y = int(radius * math.sin(angle))
        positions.append({'x': x, 'y': y})
    return positions


def _default_style() -> Dict[str, Any]:
    """Default Arrows.app style dict"""
    return {
        'font-family': 'sans-serif',
        'background-color': '#ffffff',
        'node-color': '#4C8EDA',
        'border-width': 2,
        'border-color': '#000000',
        'radius': 50,
        'node-padding': 5,
        'node-margin': 2,
        'outside-position': 'auto',
        'caption-position': 'inside',
        'caption-max-width': 200,
        'caption-color': '#ffffff',
        'caption-font-size': 16,
        'caption-font-weight': 'normal',
        'label-position': 'inside',
        'label-display': 'pill',
        'label-color': '#000000',
        'label-background-color': '#ffffff',
        'label-border-color': '#000000',
        'label-border-width': 2,
        'label-font-size': 12,
        'label-padding': 5,
        'label-margin': 4,
        'directionality': 'directed',
        'detail-position': 'inline',
        'detail-orientation': 'horizontal',
        'arrow-width': 5,
        'arrow-color': '#000000',
        'margin-start': 5,
        'margin-end': 5,
        'margin-peer': 20,
        'attachment-start': 'normal',
        'attachment-end': 'normal',
        'relationship-icon-image': '',
        'type-color': '#000000',
        'type-background-color': '#ffffff',
        'type-border-color': '#000000',
        'type-border-width': 0,
        'type-font-size': 16,
        'type-padding': 5,
        'property-position': 'outside',
        'property-alignment': 'colon',
        'property-color': '#000000',
        'property-font-size': 12,
        'property-font-weight': 'normal',
    }
