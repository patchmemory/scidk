"""
Interpreter for NC3Rs Experimental Design Assistant (EDA) files.

EDA files are ZIP archives containing JSON experimental designs.
Reference implementation: dev/code-imports/nc3rsEDA/nc3rsEDA/nc3rsEDA.py
"""

import json
import zipfile
from pathlib import Path
from typing import List, Dict, Any

# Type mapping from EDA to scidk
EDA_TO_SCIDK_TYPE = {
    'String': 'string',
    'Integer': 'number',
    'Float': 'number',
    'Boolean': 'boolean',
    'Date': 'date'
}

# Relationship type inference based on stencil pairs
RELATIONSHIP_TYPES = {
    ('Treatment', 'Subject'): 'APPLIED_TO',
    ('Subject', 'Measurement'): 'HAS_MEASUREMENT',
    ('Experiment', 'Subject'): 'INCLUDES',
    ('Group', 'Subject'): 'CONTAINS',
    ('TimePoint', 'Measurement'): 'MEASURED_AT',
    ('Subject', 'Sample'): 'HAS_SAMPLE'
}


def parse_eda_file(filepath: str) -> List[Dict[str, Any]]:
    """
    Parse .eda file (ZIP with JSON) and extract nodes.

    Args:
        filepath: Path to .eda file

    Returns:
        list: Parsed EDA nodes with structure:
            [
                {
                    'resourceId': 'n0',
                    'stencil': {'id': 'Treatment'},
                    'properties': {...},
                    'propertyTypes': {...},
                    'outgoing': [...],
                    'incoming': [...]
                },
                ...
            ]

    Raises:
        FileNotFoundError: If file doesn't exist
        ValueError: If file format is invalid
    """
    path = Path(filepath)
    if not path.exists():
        raise FileNotFoundError(f"EDA file not found: {filepath}")

    if not path.suffix == '.eda':
        raise ValueError(f"Not an EDA file: {filepath}")

    # Extract JSON from ZIP
    with zipfile.ZipFile(filepath, 'r') as zip_ref:
        # EDA files typically have a single JSON file named 'model'
        json_files = [f for f in zip_ref.namelist() if f.endswith('.json') or f == 'model']

        if not json_files:
            # Try reading first file
            if len(zip_ref.namelist()) > 0:
                json_files = [zip_ref.namelist()[0]]
            else:
                raise ValueError("EDA file is empty")

        json_content = zip_ref.read(json_files[0])
        data = json.loads(json_content)

    # EDA files contain a top-level object with childShapes array
    nodes = []
    edges = []

    if isinstance(data, dict):
        # Standard EDA format has childShapes array
        if 'childShapes' in data:
            for shape in data['childShapes']:
                # Edges have 'target' field
                if 'target' in shape:
                    edges.append(shape)
                else:
                    nodes.append(shape)
        else:
            # Single node format
            nodes = [data]
    elif isinstance(data, list):
        # Array of nodes
        for item in data:
            if isinstance(item, dict) and 'target' in item:
                edges.append(item)
            else:
                nodes.append(item)
    else:
        raise ValueError("Invalid EDA file format: expected JSON object or array")

    return nodes, edges


def eda_to_labels(eda_nodes: List[Dict[str, Any]], eda_edges: List[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    """
    Convert EDA nodes to scidk Label definitions.

    Args:
        eda_nodes: List of parsed EDA nodes
        eda_edges: List of parsed EDA edges (optional, can also extract from node outgoing/incoming)

    Returns:
        list: Label definitions ready for LabelService.create_label()
    """
    if eda_edges is None:
        eda_edges = []

    labels = []
    node_map = {}  # resourceId -> label name
    stencil_map = {}  # resourceId -> stencil type

    # First pass: create labels from nodes
    for node in eda_nodes:
        resource_id = node.get('resourceId')
        stencil_id = node.get('stencil', {}).get('id', 'Unknown')

        if not resource_id or not stencil_id:
            continue

        node_map[resource_id] = stencil_id
        stencil_map[resource_id] = stencil_id

        # Convert properties
        properties = []
        node_props = node.get('properties', {})
        prop_types = node.get('propertyTypes', {})

        for prop_name in node_props.keys():
            eda_type = prop_types.get(prop_name, 'String')
            scidk_type = EDA_TO_SCIDK_TYPE.get(eda_type, 'string')

            properties.append({
                'name': prop_name,
                'type': scidk_type,
                'required': False
            })

        # Check if label already exists
        existing_label = next((l for l in labels if l['name'] == stencil_id), None)

        if existing_label:
            # Merge properties (avoid duplicates)
            for prop in properties:
                if not any(p['name'] == prop['name'] for p in existing_label['properties']):
                    existing_label['properties'].append(prop)
        else:
            labels.append({
                'name': stencil_id,
                'properties': properties,
                'relationships': []
            })

    # Second pass: add relationships from node outgoing arrays
    label_dict = {l['name']: l for l in labels}

    for node in eda_nodes:
        resource_id = node.get('resourceId')
        from_stencil = stencil_map.get(resource_id)

        if not from_stencil or from_stencil not in label_dict:
            continue

        # Process outgoing relationships
        for outgoing in node.get('outgoing', []):
            # Try both 'target' and 'resourceId' fields
            target_id = outgoing.get('target')
            if not target_id:
                target_id = outgoing.get('resourceId')

            to_stencil = stencil_map.get(target_id)

            if not to_stencil:
                continue

            # Infer relationship type
            rel_type = RELATIONSHIP_TYPES.get((from_stencil, to_stencil), 'RELATED_TO')

            # Check if relationship already exists
            existing_rel = any(
                r['type'] == rel_type and r['target_label'] == to_stencil
                for r in label_dict[from_stencil]['relationships']
            )

            if not existing_rel:
                label_dict[from_stencil]['relationships'].append({
                    'type': rel_type,
                    'target_label': to_stencil,
                    'properties': []
                })

    # Third pass: add relationships from explicit edge objects
    for edge in eda_edges:
        edge_type = edge.get('stencil', {}).get('id', 'RELATED_TO')

        # Find source and target
        incoming_id = None
        outgoing_id = None

        if 'incoming' in edge and len(edge['incoming']) > 0:
            incoming_id = edge['incoming'][0].get('resourceId')
        if 'outgoing' in edge and len(edge['outgoing']) > 0:
            outgoing_id = edge['outgoing'][0].get('resourceId')

        if not incoming_id or not outgoing_id:
            continue

        from_stencil = stencil_map.get(incoming_id)
        to_stencil = stencil_map.get(outgoing_id)

        if not from_stencil or not to_stencil:
            continue

        if from_stencil not in label_dict:
            continue

        # Check if relationship already exists
        existing_rel = any(
            r['type'] == edge_type and r['target_label'] == to_stencil
            for r in label_dict[from_stencil]['relationships']
        )

        if not existing_rel:
            label_dict[from_stencil]['relationships'].append({
                'type': edge_type,
                'target_label': to_stencil,
                'properties': []
            })

    return labels
