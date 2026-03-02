"""
Bruker MicroCT Complete Dataset Interpreter

Interprets complete Bruker SkyScan microCT dataset folders including raw acquisition,
reconstruction, and analysis stages. Creates ImagingDataset, InstrumentRecord, and
FileSet nodes per the SciDK imaging data model.

This is a composite interpreter that understands the canonical Bruker dataset structure
and creates appropriate graph nodes for each workflow stage.
"""
from pathlib import Path
from typing import Dict, List, Any
import re


class BrukerMicroCtDatasetInterpreter:
    """Composite interpreter for complete Bruker microCT dataset folders."""

    id = "bruker_microct_dataset"
    name = "Bruker MicroCT Dataset"
    version = "1.0.0"
    extensions = []  # Triggered by directory structure, not extension
    default_enabled = True

    def interpret(self, file_path: Path) -> Dict[str, Any]:
        """Interpret complete Bruker microCT dataset directory.

        Expected structure:
            dataset/
            ├── dataset.log             # Acquisition metadata (REQUIRED)
            ├── dataset_????????.tif    # Raw TIFF stack
            ├── dataset_Rec/            # Reconstruction folder
            │   ├── dataset_rec.log     # Reconstruction metadata
            │   └── dataset_rec????????.tif  # Reconstructed TIFF stack
            └── dataset_Rec-nii-*/      # Optional analysis outputs
                └── *.nii, *.nii.gz

        Args:
            file_path: Path to dataset directory OR to .log file

        Returns:
            Dict with status, data, nodes, and relationships keys
        """
        # Determine if path is directory or log file
        if file_path.is_file() and file_path.suffix == '.log':
            dataset_dir = file_path.parent
            log_file = file_path
        elif file_path.is_dir():
            dataset_dir = file_path
            # Look for log file in directory
            log_files = list(dataset_dir.glob("*.log"))
            # Filter out reconstruction logs
            log_files = [f for f in log_files if not f.stem.endswith('_rec')]
            if not log_files:
                return {
                    'status': 'error',
                    'data': {'error': 'No acquisition .log file found in directory'}
                }
            log_file = log_files[0]
        else:
            return {
                'status': 'error',
                'data': {'error': 'Path must be a directory or .log file'}
            }

        try:
            # Extract dataset name from log file
            dataset_name = log_file.stem
            dataset_path = str(dataset_dir.resolve())

            # Parse acquisition log
            acquisition_meta = self._parse_log_file(log_file)

            # Detect raw TIFF stack
            raw_tiff_pattern = f"{dataset_name}????????.tif"
            raw_tiff_files = sorted(dataset_dir.glob(raw_tiff_pattern))

            # Detect reconstruction directory
            rec_dir = None
            for variant in [f"{dataset_name}_Rec", f"{dataset_name}_rec", f"{dataset_name}Rec"]:
                potential_dir = dataset_dir / variant
                if potential_dir.exists() and potential_dir.is_dir():
                    rec_dir = potential_dir
                    break

            # Detect analysis directory
            analysis_dirs = list(dataset_dir.glob(f"{dataset_name}_Rec-nii-*"))
            analysis_dir = analysis_dirs[0] if analysis_dirs else None

            # Build nodes
            nodes = []
            relationships = []

            # 1. ImagingDataset node (primary entity)
            imaging_props = {
                'id': dataset_name,
                'path': dataset_path,
                'modality': 'microCT',
                'instrument_vendor': 'Bruker',
            }

            # Add critical metadata from acquisition log
            if acquisition_meta:
                if 'Image Pixel Size (um)' in acquisition_meta:
                    imaging_props['voxel_size_um'] = self._parse_float(acquisition_meta['Image Pixel Size (um)'])
                elif 'Voxel size (um)' in acquisition_meta:
                    imaging_props['voxel_size_um'] = self._parse_float(acquisition_meta['Voxel size (um)'])
                elif 'Pixel Size (um)' in acquisition_meta:
                    imaging_props['voxel_size_um'] = self._parse_float(acquisition_meta['Pixel Size (um)'])

                if 'Study Date and Time' in acquisition_meta:
                    imaging_props['acquisition_date'] = acquisition_meta['Study Date and Time']
                if 'Scanner' in acquisition_meta:
                    imaging_props['instrument'] = acquisition_meta['Scanner']

            imaging_node = {
                'label': 'ImagingDataset',
                'key_property': 'path',
                'properties': imaging_props
            }
            nodes.append(imaging_node)

            # 2. InstrumentRecord node (from acquisition metadata)
            if acquisition_meta:
                instrument_props = {
                    'source_file': str(log_file.resolve()),
                    'instrument_type': 'Bruker SkyScan microCT',
                }

                # Add instrument parameters
                param_map = {
                    'Source Voltage (kV)': 'voltage_kv',
                    'Source Current (uA)': 'current_ua',
                    'Exposure (ms)': 'exposure_ms',
                    'Rotation Step (deg)': 'rotation_step_deg',
                    'Camera Pixel Size (um)': 'camera_pixel_size_um',
                    'Filter': 'filter',
                }

                for log_key, prop_name in param_map.items():
                    if log_key in acquisition_meta:
                        value = acquisition_meta[log_key]
                        # Try to convert to float if it looks numeric
                        if log_key != 'Filter':
                            value = self._parse_float(value)
                        instrument_props[prop_name] = value

                if 'Reconstruction Program' in acquisition_meta:
                    instrument_props['reconstruction_software'] = acquisition_meta['Reconstruction Program']

                instrument_node = {
                    'label': 'InstrumentRecord',
                    'key_property': 'source_file',
                    'properties': instrument_props
                }
                nodes.append(instrument_node)

                # Relationship: ImagingDataset -> InstrumentRecord
                relationships.append({
                    'type': 'METADATA_SOURCE',
                    'from_label': 'ImagingDataset',
                    'from_match': {'path': dataset_path},
                    'to_label': 'InstrumentRecord',
                    'to_match': {'source_file': str(log_file.resolve())}
                })

            # 3. FileSet node for raw TIFF stack
            if raw_tiff_files:
                raw_fileset_props = {
                    'id': f"{dataset_name}_raw",
                    'stage': 'raw',
                    'file_count': len(raw_tiff_files),
                    'format': 'TIFF',
                    'pattern': raw_tiff_pattern,
                    'path': dataset_path,
                    'first_file': raw_tiff_files[0].name,
                    'last_file': raw_tiff_files[-1].name
                }

                # Get dimensions from first TIFF if possible
                if 'Number Of Rows' in acquisition_meta and 'Number Of Columns' in acquisition_meta:
                    rows = self._parse_int(acquisition_meta['Number Of Rows'])
                    cols = self._parse_int(acquisition_meta['Number Of Columns'])
                    if rows and cols:
                        raw_fileset_props['dimensions'] = f"{cols}x{rows}"

                if 'Depth (bits)' in acquisition_meta:
                    raw_fileset_props['bit_depth'] = self._parse_int(acquisition_meta['Depth (bits)'])

                raw_fileset_node = {
                    'label': 'FileSet',
                    'key_property': 'id',
                    'properties': raw_fileset_props
                }
                nodes.append(raw_fileset_node)

                # Relationship: ImagingDataset -> FileSet (raw)
                relationships.append({
                    'type': 'RAW_DATA',
                    'from_label': 'ImagingDataset',
                    'from_match': {'path': dataset_path},
                    'to_label': 'FileSet',
                    'to_match': {'id': f"{dataset_name}_raw"}
                })

            # 4. FileSet node for reconstructed TIFF stack
            if rec_dir:
                rec_tiff_pattern = f"{dataset_name}_rec????????.tif"
                rec_tiff_files = sorted(rec_dir.glob(rec_tiff_pattern))

                if rec_tiff_files:
                    rec_fileset_props = {
                        'id': f"{dataset_name}_reconstructed",
                        'stage': 'reconstructed',
                        'file_count': len(rec_tiff_files),
                        'format': 'TIFF',
                        'pattern': rec_tiff_pattern,
                        'path': str(rec_dir.resolve()),
                        'first_file': rec_tiff_files[0].name,
                        'last_file': rec_tiff_files[-1].name
                    }

                    rec_fileset_node = {
                        'label': 'FileSet',
                        'key_property': 'id',
                        'properties': rec_fileset_props
                    }
                    nodes.append(rec_fileset_node)

                    # Relationship: ImagingDataset -> FileSet (reconstructed)
                    relationships.append({
                        'type': 'RECONSTRUCTED',
                        'from_label': 'ImagingDataset',
                        'from_match': {'path': dataset_path},
                        'to_label': 'FileSet',
                        'to_match': {'id': f"{dataset_name}_reconstructed"}
                    })

            # 5. FileSet node for analysis outputs (NIfTI files)
            if analysis_dir:
                nifti_files = list(analysis_dir.glob("*.nii")) + list(analysis_dir.glob("*.nii.gz"))

                if nifti_files:
                    analysis_fileset_props = {
                        'id': f"{dataset_name}_analysis",
                        'stage': 'analysis',
                        'file_count': len(nifti_files),
                        'format': 'NIfTI',
                        'path': str(analysis_dir.resolve()),
                        'files': [f.name for f in sorted(nifti_files)]
                    }

                    analysis_fileset_node = {
                        'label': 'FileSet',
                        'key_property': 'id',
                        'properties': analysis_fileset_props
                    }
                    nodes.append(analysis_fileset_node)

                    # Relationship: ImagingDataset -> FileSet (analysis)
                    relationships.append({
                        'type': 'ANALYSIS',
                        'from_label': 'ImagingDataset',
                        'from_match': {'path': dataset_path},
                        'to_label': 'FileSet',
                        'to_match': {'id': f"{dataset_name}_analysis"}
                    })

            # Build summary data
            data = {
                'dataset_id': dataset_name,
                'dataset_path': dataset_path,
                'voxel_size_um': imaging_props.get('voxel_size_um'),
                'stages': {
                    'raw': len(raw_tiff_files) if raw_tiff_files else 0,
                    'reconstructed': len(rec_tiff_files) if rec_dir and 'rec_tiff_files' in locals() else 0,
                    'analysis': len(nifti_files) if analysis_dir and 'nifti_files' in locals() else 0
                },
                'total_files': (len(raw_tiff_files) if raw_tiff_files else 0) +
                               (len(rec_tiff_files) if rec_dir and 'rec_tiff_files' in locals() else 0) +
                               (len(nifti_files) if analysis_dir and 'nifti_files' in locals() else 0),
                'node_count': len(nodes),
                'relationship_count': len(relationships)
            }

            return {
                'status': 'success',
                'data': data,
                'nodes': nodes,
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

    def _parse_log_file(self, log_path: Path) -> Dict[str, str]:
        """Parse Bruker SkyScan log file into key-value dictionary."""
        parsed = {}
        try:
            with open(log_path, 'r', encoding='utf-8', errors='ignore') as f:
                for line in f:
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

                    if len(parts) == 2:
                        key = parts[0].strip()
                        value = parts[1].strip()
                        parsed[key] = value
        except Exception:
            pass

        return parsed

    def _parse_float(self, value: Any) -> Any:
        """Try to parse value as float, return as-is if it fails."""
        try:
            return float(value)
        except (ValueError, TypeError):
            return value

    def _parse_int(self, value: Any) -> Any:
        """Try to parse value as int, return None if it fails."""
        try:
            return int(value)
        except (ValueError, TypeError):
            return None
