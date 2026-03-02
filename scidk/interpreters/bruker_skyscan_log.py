"""
Bruker SkyScan microCT Log File Interpreter

Parses Bruker SkyScan acquisition .log files and creates ImagingDataset and
InstrumentRecord nodes in the knowledge graph.

This interpreter declares domain nodes that are written to Neo4j at commit time,
demonstrating the Phase 1 interpreter contract extension.
"""
from pathlib import Path
from typing import Dict, Any


class BrukerSkyScanLogInterpreter:
    """Interpreter for Bruker SkyScan microCT .log files.

    Parses key-value pairs from acquisition logs and declares ImagingDataset
    and InstrumentRecord nodes with parsed properties.
    """

    id = "bruker_skyscan_log"
    name = "Bruker SkyScan Log"
    version = "1.0.0"
    extensions = [".log"]

    # Known field mappings: log key -> (target_node, property_name, converter)
    FIELD_MAP = {
        'Voxel size (um)': ('imaging', 'voxel_size_um', float),
        'Source Voltage (kV)': ('instrument', 'voltage_kv', float),
        'Source Current (uA)': ('instrument', 'current_ua', float),
        'Exposure (ms)': ('instrument', 'exposure_ms', float),
        'Rotation Step (deg)': ('instrument', 'rotation_step_deg', float),
        'Number of Files': ('imaging', 'file_count', int),
        'Image Pixel Size (um)': ('imaging', 'pixel_size_um', float),
        'Camera Pixel Size (um)': ('instrument', 'camera_pixel_size_um', float),
        'Object to Source (mm)': ('instrument', 'object_to_source_mm', float),
        'Camera to Source (mm)': ('instrument', 'camera_to_source_mm', float),
        'Filter': ('instrument', 'filter', str),
        'Scanning position': ('imaging', 'scanning_position', str),
        'Depth (mm)': ('imaging', 'depth_mm', float),
        'Number of Rows': ('imaging', 'rows', int),
        'Number of Columns': ('imaging', 'columns', int),
    }

    def interpret(self, file_path: Path) -> Dict[str, Any]:
        """Parse Bruker SkyScan .log file and declare domain nodes.

        Args:
            file_path: Path to the .log file

        Returns:
            Dict with status, data, nodes, and relationships keys
        """
        try:
            # Read and parse log file
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                lines = f.readlines()

            # Detect Bruker SkyScan format
            content = ''.join(lines[:30]).lower()
            if 'skyscan' not in content and not any(key in '\n'.join(lines[:50]) for key in ['Voxel size (um)', 'Source Voltage (kV)']):
                return {
                    'status': 'error',
                    'data': {'error': 'Not a Bruker SkyScan log file'}
                }

            # Parse key-value pairs
            parsed = {}
            imaging_props = {}
            instrument_props = {}

            for line in lines:
                line = line.strip()
                if not line or line.startswith('['):
                    continue

                # Split on '=' or tab
                if '=' in line:
                    parts = line.split('=', 1)
                elif '\t' in line:
                    parts = line.split('\t', 1)
                else:
                    continue

                if len(parts) != 2:
                    continue

                key = parts[0].strip()
                value = parts[1].strip()

                # Store raw
                parsed[key] = value

                # Map to typed properties
                if key in self.FIELD_MAP:
                    target, prop_name, converter = self.FIELD_MAP[key]
                    try:
                        converted = converter(value)
                        if target == 'imaging':
                            imaging_props[prop_name] = converted
                        elif target == 'instrument':
                            instrument_props[prop_name] = converted
                    except (ValueError, TypeError):
                        # Skip unconvertible values
                        pass

            # Determine dataset path (parent directory of log file)
            dataset_path = str(file_path.parent.resolve())

            # Build ImagingDataset node declaration
            imaging_node = {
                'label': 'ImagingDataset',
                'key_property': 'path',
                'properties': {
                    'path': dataset_path,
                    'modality': 'microCT',
                    'instrument': 'Bruker SkyScan',
                    **imaging_props
                }
            }

            # Build InstrumentRecord node declaration
            instrument_node = {
                'label': 'InstrumentRecord',
                'key_property': 'source_file',
                'properties': {
                    'source_file': str(file_path.resolve()),
                    'instrument_type': 'Bruker SkyScan microCT',
                    **instrument_props
                }
            }

            # Declare relationships
            relationships = [
                {
                    'type': 'METADATA_SOURCE',
                    'from_label': 'ImagingDataset',
                    'from_match': {'path': dataset_path},
                    'to_label': 'InstrumentRecord',
                    'to_match': {'source_file': str(file_path.resolve())}
                },
                {
                    'type': 'DERIVED_FROM',
                    'from_label': 'ImagingDataset',
                    'from_match': {'path': dataset_path},
                    'to_label': 'File',
                    'to_match': {'path': str(file_path.resolve())}
                }
            ]

            return {
                'status': 'success',
                'data': {
                    'raw_fields': parsed,
                    'imaging_properties': imaging_props,
                    'instrument_properties': instrument_props
                },
                'nodes': [imaging_node, instrument_node],
                'relationships': relationships
            }

        except Exception as e:
            return {
                'status': 'error',
                'data': {
                    'error': str(e),
                    'error_type': type(e).__name__
                }
            }
