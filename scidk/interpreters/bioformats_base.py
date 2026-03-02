"""
Bio-Formats Base Interpreter

Wraps Bio-Formats command line tools (showinf/bfconvert) to interpret
microscopy image formats supported by Bio-Formats. This provides a pathway
for standard microscopy formats while custom preclinical interpreters handle
specialized formats not covered by Bio-Formats.

Uses CLI tools rather than python-bioformats to avoid Java/javabridge dependencies.
"""
from pathlib import Path
from typing import Dict, Any, Optional
import subprocess
import xml.etree.ElementTree as ET
import shutil


class BioFormatsInterpreter:
    """
    Base interpreter using Bio-Formats CLI tools (showinf).

    This class provides metadata extraction via the showinf command line tool.
    Subclasses should extend this to handle specific file formats.

    Installation:
        Download bftools.zip from bio-formats.readthedocs.io OR
        conda install ome::bftools
    """

    id = "bioformats_base"
    name = "Bio-Formats Base"
    version = "1.0.0"
    extensions = []  # Subclasses override
    default_enabled = True

    # Namespace for OME-XML parsing
    OME_NS = {'ome': 'http://www.openmicroscopy.org/Schemas/OME/2016-06'}

    def __init__(self):
        self._showinf_path = None
        self._bfconvert_path = None

    def interpret(self, file_path: Path) -> Dict[str, Any]:
        """
        Interpret an image file using Bio-Formats showinf tool.

        Args:
            file_path: Path to image file

        Returns:
            Dict with status, data, nodes, and relationships keys
        """
        if not file_path.exists():
            return {
                'status': 'error',
                'data': {
                    'error': 'File not found',
                    'path': str(file_path)
                }
            }

        # Check if showinf is available
        showinf_path = self._find_showinf()
        if not showinf_path:
            return {
                'status': 'error',
                'data': {
                    'error': 'Bio-Formats showinf tool not found. Install with: conda install ome::bftools',
                    'error_type': 'BIOFORMATS_NOT_INSTALLED',
                    'path': str(file_path)
                }
            }

        try:
            # Run showinf to extract OME-XML metadata
            # -nopix: Don't read pixel data (faster)
            # -omexml-only: Only output OME-XML
            result = subprocess.run(
                [showinf_path, '-nopix', '-omexml-only', str(file_path)],
                capture_output=True,
                text=True,
                timeout=30  # 30 second timeout
            )

            if result.returncode != 0:
                return {
                    'status': 'error',
                    'data': {
                        'error': f'Bio-Formats showinf failed: {result.stderr}',
                        'error_type': 'BIOFORMATS_EXECUTION_ERROR',
                        'path': str(file_path),
                        'returncode': result.returncode
                    }
                }

            # Parse OME-XML from stdout
            ome_xml = result.stdout
            if not ome_xml or '<OME' not in ome_xml:
                return {
                    'status': 'error',
                    'data': {
                        'error': 'No OME-XML metadata found in showinf output',
                        'error_type': 'NO_OME_XML',
                        'path': str(file_path)
                    }
                }

            # Extract metadata from OME-XML
            metadata = self._parse_ome_xml(ome_xml)

            # Build nodes and relationships
            nodes = []
            relationships = []

            # 1. ImagingDataset node
            imaging_props = {
                'path': str(file_path.resolve()),
                'modality': metadata.get('modality', 'unknown'),
            }

            # Add voxel/pixel dimensions (critical for imaging)
            if 'physical_size_x' in metadata or 'physical_size_y' in metadata or 'physical_size_z' in metadata:
                if 'physical_size_x' in metadata and 'physical_size_y' in metadata:
                    # For 2D images, report pixel size
                    imaging_props['pixel_size_um'] = {
                        'x': metadata['physical_size_x'],
                        'y': metadata['physical_size_y']
                    }
                if 'physical_size_z' in metadata:
                    imaging_props['voxel_size_um'] = metadata['physical_size_z']

            # Image dimensions
            if 'size_x' in metadata and 'size_y' in metadata:
                imaging_props['dimensions'] = f"{metadata['size_x']}x{metadata['size_y']}"
                if 'size_z' in metadata and metadata['size_z'] > 1:
                    imaging_props['dimensions'] += f"x{metadata['size_z']}"

            # Channels and timepoints
            if 'size_c' in metadata and metadata['size_c'] > 1:
                imaging_props['channels'] = metadata['size_c']
            if 'size_t' in metadata and metadata['size_t'] > 1:
                imaging_props['timepoints'] = metadata['size_t']

            # Acquisition date
            if 'acquisition_date' in metadata:
                imaging_props['acquisition_date'] = metadata['acquisition_date']

            imaging_node = {
                'label': 'ImagingDataset',
                'key_property': 'path',
                'properties': imaging_props
            }
            nodes.append(imaging_node)

            # 2. InstrumentRecord node
            instrument_props = {
                'source_file': str(file_path.resolve()),
                'instrument_type': 'Bio-Formats Supported Format',
            }

            # Add instrument metadata if available
            if 'instrument_manufacturer' in metadata:
                instrument_props['manufacturer'] = metadata['instrument_manufacturer']
            if 'instrument_model' in metadata:
                instrument_props['model'] = metadata['instrument_model']
            if 'objective_model' in metadata:
                instrument_props['objective'] = metadata['objective_model']
            if 'objective_na' in metadata:
                instrument_props['numerical_aperture'] = metadata['objective_na']
            if 'objective_magnification' in metadata:
                instrument_props['magnification'] = metadata['objective_magnification']

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
                'from_match': {'path': str(file_path.resolve())},
                'to_label': 'InstrumentRecord',
                'to_match': {'source_file': str(file_path.resolve())}
            })

            return {
                'status': 'success',
                'data': {
                    'format': metadata.get('format', 'unknown'),
                    'modality': metadata.get('modality', 'unknown'),
                    'dimensions': imaging_props.get('dimensions'),
                    'channels': metadata.get('size_c', 1),
                    'timepoints': metadata.get('size_t', 1),
                    'z_slices': metadata.get('size_z', 1),
                    'raw_metadata': metadata
                },
                'nodes': nodes,
                'relationships': relationships
            }

        except subprocess.TimeoutExpired:
            return {
                'status': 'error',
                'data': {
                    'error': 'Bio-Formats showinf timed out (>30s)',
                    'error_type': 'TIMEOUT',
                    'path': str(file_path)
                }
            }
        except Exception as e:
            return {
                'status': 'error',
                'data': {
                    'error': f'Failed to interpret with Bio-Formats: {str(e)}',
                    'error_type': type(e).__name__,
                    'path': str(file_path)
                }
            }

    def _find_showinf(self) -> Optional[str]:
        """Find showinf executable in PATH or common locations."""
        if self._showinf_path:
            return self._showinf_path

        # Check if showinf is in PATH
        path = shutil.which('showinf')
        if path:
            self._showinf_path = path
            return path

        # Check common conda location
        home = Path.home()
        conda_paths = [
            home / 'miniconda3' / 'bin' / 'showinf',
            home / 'anaconda3' / 'bin' / 'showinf',
            Path('/opt/conda/bin/showinf'),
            Path('/usr/local/bin/showinf'),
        ]

        for conda_path in conda_paths:
            if conda_path.exists():
                self._showinf_path = str(conda_path)
                return str(conda_path)

        return None

    def _parse_ome_xml(self, ome_xml: str) -> Dict[str, Any]:
        """
        Parse OME-XML and extract key imaging metadata.

        Args:
            ome_xml: OME-XML string from showinf

        Returns:
            Dict of parsed metadata
        """
        metadata = {}

        try:
            # Parse XML
            root = ET.fromstring(ome_xml)

            # Update namespace based on actual XML
            ns = {'ome': root.tag.split('}')[0].strip('{')} if '}' in root.tag else self.OME_NS

            # Extract Image metadata
            image = root.find('.//ome:Image', ns)
            if image is not None:
                # Image name
                name_elem = image.find('ome:Name', ns)
                if name_elem is not None and name_elem.text:
                    metadata['image_name'] = name_elem.text

                # Acquisition date
                acq_date = image.find('ome:AcquisitionDate', ns)
                if acq_date is not None and acq_date.text:
                    metadata['acquisition_date'] = acq_date.text

                # Pixels element (contains dimensions)
                pixels = image.find('.//ome:Pixels', ns)
                if pixels is not None:
                    # Format/Type
                    if 'Type' in pixels.attrib:
                        metadata['pixel_type'] = pixels.attrib['Type']

                    # Dimensions
                    for dim in ['SizeX', 'SizeY', 'SizeZ', 'SizeC', 'SizeT']:
                        if dim in pixels.attrib:
                            key = f"size_{dim[-1].lower()}"
                            metadata[key] = int(pixels.attrib[dim])

                    # Physical dimensions (voxel/pixel size in micrometers)
                    for dim in ['PhysicalSizeX', 'PhysicalSizeY', 'PhysicalSizeZ']:
                        if dim in pixels.attrib:
                            key = f"physical_{dim.replace('PhysicalSize', 'size_').lower()}"
                            try:
                                metadata[key] = float(pixels.attrib[dim])
                            except ValueError:
                                pass

                    # Channel information
                    channels = pixels.findall('ome:Channel', ns)
                    if channels:
                        channel_names = []
                        for ch in channels:
                            if 'Name' in ch.attrib:
                                channel_names.append(ch.attrib['Name'])
                        if channel_names:
                            metadata['channel_names'] = channel_names

            # Extract Instrument metadata
            instrument = root.find('.//ome:Instrument', ns)
            if instrument is not None:
                # Microscope
                microscope = instrument.find('ome:Microscope', ns)
                if microscope is not None:
                    if 'Manufacturer' in microscope.attrib:
                        metadata['instrument_manufacturer'] = microscope.attrib['Manufacturer']
                    if 'Model' in microscope.attrib:
                        metadata['instrument_model'] = microscope.attrib['Model']

                # Objective
                objective = instrument.find('.//ome:Objective', ns)
                if objective is not None:
                    if 'Model' in objective.attrib:
                        metadata['objective_model'] = objective.attrib['Model']
                    if 'NominalMagnification' in objective.attrib:
                        try:
                            metadata['objective_magnification'] = float(objective.attrib['NominalMagnification'])
                        except ValueError:
                            pass
                    if 'LensNA' in objective.attrib:
                        try:
                            metadata['objective_na'] = float(objective.attrib['LensNA'])
                        except ValueError:
                            pass

            # Determine modality from format/metadata
            metadata['modality'] = self._infer_modality(metadata)

        except ET.ParseError as e:
            metadata['parse_error'] = f'Failed to parse OME-XML: {str(e)}'
        except Exception as e:
            metadata['parse_error'] = f'Error extracting metadata: {str(e)}'

        return metadata

    def _infer_modality(self, metadata: Dict[str, Any]) -> str:
        """
        Infer imaging modality from available metadata.

        Bio-Formats primarily handles microscopy, so default to that.
        Subclasses can override for specific modalities.
        """
        # Check instrument type
        if 'instrument_model' in metadata:
            model = metadata['instrument_model'].lower()
            if 'confocal' in model:
                return 'confocal_microscopy'
            if 'widefield' in model:
                return 'widefield_microscopy'

        # Check channel count (multi-channel often indicates fluorescence)
        if metadata.get('size_c', 1) > 1:
            return 'fluorescence_microscopy'

        # Check z-stack (indicates 3D microscopy)
        if metadata.get('size_z', 1) > 1:
            return '3d_microscopy'

        # Default to microscopy
        return 'microscopy'
