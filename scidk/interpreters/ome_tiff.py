"""
OME-TIFF Interpreter

Interprets OME-TIFF (Open Microscopy Environment TIFF) files using Bio-Formats.
OME-TIFF is a widely-used format in microscopy that embeds rich OME-XML metadata
within TIFF files.

This interpreter routes OME-TIFF files through Bio-Formats for comprehensive
metadata extraction, while plain TIFF files continue to use the lightweight
TIFF interpreter.
"""
from pathlib import Path
from typing import Dict, Any

from .bioformats_base import BioFormatsInterpreter


class OMETiffInterpreter(BioFormatsInterpreter):
    """
    Interpreter for OME-TIFF files using Bio-Formats.

    OME-TIFF files contain OME-XML metadata describing:
    - Multi-dimensional image data (X, Y, Z, C, T)
    - Physical dimensions (voxel/pixel sizes)
    - Instrument configuration
    - Acquisition parameters
    - Channel information

    Commonly used in:
    - Confocal microscopy (Zeiss, Leica, Nikon)
    - Widefield fluorescence microscopy
    - High-content screening
    - Time-lapse imaging
    """

    id = "ome_tiff"
    name = "OME-TIFF Interpreter"
    version = "1.0.0"
    extensions = [".ome.tif", ".ome.tiff"]
    default_enabled = True

    def interpret(self, file_path: Path) -> Dict[str, Any]:
        """
        Interpret OME-TIFF file using Bio-Formats.

        Args:
            file_path: Path to .ome.tif or .ome.tiff file

        Returns:
            Dict with status, data, nodes, and relationships keys
        """
        # Use parent Bio-Formats implementation
        result = super().interpret(file_path)

        # Enhance result with OME-TIFF specific information
        if result['status'] == 'success':
            result['data']['format'] = 'OME-TIFF'

            # Mark as OME-TIFF in ImagingDataset node
            for node in result.get('nodes', []):
                if node.get('label') == 'ImagingDataset':
                    node['properties']['format'] = 'OME-TIFF'
                    # OME-TIFF is typically from microscopy
                    if node['properties'].get('modality') == 'unknown':
                        node['properties']['modality'] = 'microscopy'

        return result

    def _infer_modality(self, metadata: Dict[str, Any]) -> str:
        """
        Infer modality for OME-TIFF files.

        OME-TIFF is primarily used in microscopy applications.
        """
        # Check for multi-channel (common in fluorescence)
        if metadata.get('size_c', 1) > 1:
            return 'fluorescence_microscopy'

        # Check for z-stack (3D microscopy)
        if metadata.get('size_z', 1) > 1:
            return '3d_microscopy'

        # Check for time series
        if metadata.get('size_t', 1) > 1:
            return 'timelapse_microscopy'

        # Check instrument manufacturer
        if 'instrument_manufacturer' in metadata:
            manufacturer = metadata['instrument_manufacturer'].lower()
            if 'zeiss' in manufacturer or 'leica' in manufacturer or 'nikon' in manufacturer:
                return 'confocal_microscopy'

        # Default to microscopy
        return 'microscopy'
