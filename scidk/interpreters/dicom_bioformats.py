"""
DICOM Bio-Formats Interpreter

Interprets DICOM medical imaging files using Bio-Formats. While Bio-Formats'
DICOM support focuses on specific microscopy-adjacent use cases, it provides
a standardized pathway for DICOM metadata extraction through OME-XML conversion.

This interpreter coexists with the legacy pydicom-based interpreter
(interpreters/imaging/dicom.py) and provides an alternative pathway for
DICOM files that Bio-Formats supports well (e.g., multi-frame DICOM,
certain proprietary DICOM variants).

Note: For clinical DICOM (MRI, CT, PET), the pydicom-based interpreter
may be more appropriate. This interpreter is intended for research/microscopy
DICOM workflows where Bio-Formats integration is beneficial.
"""
from pathlib import Path
from typing import Dict, Any

from .bioformats_base import BioFormatsInterpreter


class DicomBioFormatsInterpreter(BioFormatsInterpreter):
    """
    Interpreter for DICOM files using Bio-Formats.

    Extracts metadata from DICOM files through Bio-Formats' DICOM reader,
    which converts DICOM metadata to OME-XML for standardized parsing.

    Use cases:
    - Multi-frame DICOM
    - Research/preclinical imaging DICOM
    - DICOM files from microscopy-adjacent modalities
    - Standardized OME-XML representation of DICOM metadata

    For clinical DICOM (MRI, CT, PET), consider using the pydicom-based
    interpreter which provides modality-specific parameter extraction.
    """

    id = "dicom_bioformats"
    name = "DICOM Bio-Formats Interpreter"
    version = "1.0.0"
    extensions = [".dcm", ".dicom"]
    default_enabled = False  # Coexists with legacy DICOM interpreter

    def interpret(self, file_path: Path) -> Dict[str, Any]:
        """
        Interpret DICOM file using Bio-Formats.

        Args:
            file_path: Path to .dcm or .dicom file

        Returns:
            Dict with status, data, nodes, and relationships keys
        """
        # Use parent Bio-Formats implementation
        result = super().interpret(file_path)

        # Enhance result with DICOM-specific information
        if result['status'] == 'success':
            result['data']['format'] = 'DICOM'

            # Update nodes with DICOM-specific properties
            for node in result.get('nodes', []):
                if node.get('label') == 'ImagingDataset':
                    node['properties']['format'] = 'DICOM'
                    # Infer modality from DICOM metadata if not already set
                    if node['properties'].get('modality') == 'unknown':
                        node['properties']['modality'] = self._infer_dicom_modality(result['data'].get('raw_metadata', {}))

        return result

    def _infer_dicom_modality(self, metadata: Dict[str, Any]) -> str:
        """
        Infer imaging modality from DICOM metadata.

        DICOM files should contain modality information in the metadata,
        but Bio-Formats may not always expose it directly in OME-XML.
        """
        # Check if modality is already determined
        if 'modality' in metadata and metadata['modality'] != 'unknown':
            return metadata['modality']

        # Check for common DICOM modality indicators
        # Multi-frame often indicates dynamic imaging
        if metadata.get('size_t', 1) > 1:
            return 'dynamic_imaging'

        # Multi-slice indicates volumetric imaging
        if metadata.get('size_z', 1) > 1:
            return 'volumetric_imaging'

        # Default to generic medical imaging
        return 'medical_imaging'

    def _infer_modality(self, metadata: Dict[str, Any]) -> str:
        """Override parent's modality inference for DICOM."""
        return self._infer_dicom_modality(metadata)
