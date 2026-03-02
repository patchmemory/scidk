"""
TEMPLATE: Imaging Format Interpreter

This template demonstrates how to create a new imaging format interpreter
for SciDK. Copy this file, rename it, and follow the inline guidance.

Two main patterns for imaging interpreters:
1. Simple file-level: Parse a single metadata file (logs, headers)
2. Composite dataset: Interpret entire dataset directories with multiple files

Choose based on your format's structure. See examples below.
"""
from pathlib import Path
from typing import Dict, Any


class MyFormatInterpreter:
    """
    Interpreter for [Your Format Name] imaging files.

    [Brief description of the format - vendor, modality, use cases]

    Example formats to reference:
    - Simple file-level: BrukerSkyScanLogInterpreter (log file parsing)
    - Composite dataset: BrukerMicroCtDatasetInterpreter (directory scanning)
    - Bio-Formats routing: OMETiffInterpreter (extends BioFormatsInterpreter)
    """

    # =========================================================================
    # REQUIRED CLASS ATTRIBUTES
    # =========================================================================

    # Unique identifier (lowercase, underscores)
    # Convention: vendor_modality or format_name
    id = "my_format"

    # Human-readable name (shown in UI)
    name = "My Format Interpreter"

    # Semantic version (increment on changes)
    version = "1.0.0"

    # File extensions this interpreter handles
    # Examples:
    #   [".log"] - single extension
    #   [".dcm", ".dicom"] - multiple extensions
    #   [] - no extension (triggered by other logic, e.g., directory detection)
    extensions = [".myformat"]

    # Whether interpreter is enabled by default
    # Use False if:
    # - Coexists with another interpreter for same extension
    # - Requires external dependencies not commonly available
    # - Still experimental/beta
    default_enabled = True

    # =========================================================================
    # INITIALIZATION (Optional)
    # =========================================================================

    def __init__(self):
        """
        Initialize interpreter with any configuration.

        Optional. Only needed if you have:
        - Configuration parameters
        - Cached data structures
        - External tool paths to detect
        """
        pass

    # =========================================================================
    # MAIN INTERPRET METHOD (REQUIRED)
    # =========================================================================

    def interpret(self, file_path: Path) -> Dict[str, Any]:
        """
        Interpret an imaging file and extract metadata.

        This is the core method called by SciDK's interpretation engine.

        Args:
            file_path: Path to the file to interpret
                      Can be a metadata file, image file, or directory
                      depending on your interpreter's pattern

        Returns:
            Dict with REQUIRED keys:
            - 'status': 'success' or 'error'
            - 'data': Dict with extracted metadata (on success) or error info (on error)

            OPTIONAL keys for graph integration:
            - 'nodes': List of node declarations to create in Neo4j
            - 'relationships': List of relationship declarations

        Pattern for return structure:
        {
            'status': 'success' | 'error',
            'data': {
                # On success: your extracted metadata
                'modality': 'microCT',
                'voxel_size_um': 10.5,
                'dimensions': '512x512x200',
                # ... format-specific fields

                # On error: error information
                'error': 'Description of what went wrong',
                'error_type': 'FILE_NOT_FOUND',  # Optional categorization
                'path': str(file_path)
            },
            'nodes': [
                # Node declarations (see below for format)
            ],
            'relationships': [
                # Relationship declarations (see below for format)
            ]
        }
        """

        # ---------------------------------------------------------------------
        # STEP 1: Validate Input
        # ---------------------------------------------------------------------
        # Always check if file/directory exists first
        if not file_path.exists():
            return {
                'status': 'error',
                'data': {
                    'error': 'File not found',
                    'error_type': 'FILE_NOT_FOUND',
                    'path': str(file_path)
                }
            }

        # Check if it's the expected type (file vs directory)
        # For file-level interpreters:
        if not file_path.is_file():
            return {
                'status': 'error',
                'data': {
                    'error': 'Expected a file, got a directory',
                    'path': str(file_path)
                }
            }

        # For directory-level interpreters (composite datasets):
        # if not file_path.is_dir():
        #     return {'status': 'error', 'data': {'error': 'Expected a directory'}}

        try:
            # -----------------------------------------------------------------
            # STEP 2: Parse Metadata
            # -----------------------------------------------------------------
            # Read and parse your format
            # Examples:
            # - Text parsing: Parse log files, CSV headers, etc.
            # - Binary parsing: Use struct.unpack for binary headers
            # - XML/JSON: Use standard libraries
            # - External tools: Call CLI tools via subprocess

            # Example: Simple text parsing
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                lines = f.readlines()

            # Parse format-specific fields
            metadata = self._parse_format(lines)

            # -----------------------------------------------------------------
            # STEP 3: Build Response Data
            # -----------------------------------------------------------------
            # Structure your extracted metadata
            # Include critical imaging parameters:
            # - Modality (microCT, MRI, optical, ultrasound, etc.)
            # - Voxel/pixel sizes (in micrometers)
            # - Dimensions (WxHxD or WxH)
            # - Acquisition date/time
            # - Instrument information

            data = {
                'modality': metadata.get('modality', 'unknown'),
                'voxel_size_um': metadata.get('voxel_size'),
                'dimensions': f"{metadata.get('width')}x{metadata.get('height')}",
                'acquisition_date': metadata.get('date'),
                'instrument': metadata.get('instrument'),
                # Add format-specific fields
                'raw_metadata': metadata  # Keep all parsed data
            }

            # -----------------------------------------------------------------
            # STEP 4: Declare Graph Nodes (Optional but Recommended)
            # -----------------------------------------------------------------
            # Declare domain nodes to create in Neo4j knowledge graph
            # Common node types for imaging:
            # - ImagingDataset: The primary imaging data entity
            # - InstrumentRecord: Acquisition instrument/parameters
            # - FileSet: Collections of related files (for stacks/series)

            nodes = []
            relationships = []

            # Example 1: ImagingDataset node
            # This represents the complete imaging dataset
            imaging_node = {
                'label': 'ImagingDataset',  # Node label in Neo4j
                'key_property': 'path',      # Unique identifier property
                'properties': {
                    'path': str(file_path.parent.resolve()),  # Dataset location
                    'modality': metadata.get('modality'),
                    'instrument_vendor': 'My Vendor',
                    'voxel_size_um': metadata.get('voxel_size'),
                    'acquisition_date': metadata.get('date'),
                    # Add critical imaging parameters
                    # Prioritize: voxel size > dimensions > acquisition params
                }
            }
            nodes.append(imaging_node)

            # Example 2: InstrumentRecord node
            # This captures acquisition parameters and instrument settings
            instrument_node = {
                'label': 'InstrumentRecord',
                'key_property': 'source_file',  # Use source file as unique key
                'properties': {
                    'source_file': str(file_path.resolve()),
                    'instrument_type': 'My Instrument Type',
                    'voltage_kv': metadata.get('voltage'),
                    'current_ua': metadata.get('current'),
                    'exposure_ms': metadata.get('exposure'),
                    # Add instrument-specific parameters
                }
            }
            nodes.append(instrument_node)

            # Example 3: FileSet node (for composite interpreters)
            # Use when you have multiple files representing a single entity
            # (e.g., TIFF stacks, DICOM series)
            # fileset_node = {
            #     'label': 'FileSet',
            #     'key_property': 'id',
            #     'properties': {
            #         'id': f"{dataset_name}_raw",
            #         'stage': 'raw',  # or 'reconstructed', 'analysis'
            #         'file_count': len(tiff_files),
            #         'format': 'TIFF',
            #         'pattern': '*.tif',
            #         'path': str(dataset_dir),
            #     }
            # }
            # nodes.append(fileset_node)

            # -----------------------------------------------------------------
            # STEP 5: Declare Graph Relationships (Optional but Recommended)
            # -----------------------------------------------------------------
            # Define how nodes connect to each other
            # Common relationships:
            # - METADATA_SOURCE: ImagingDataset -> InstrumentRecord
            # - DERIVED_FROM: ImagingDataset -> File (the metadata source file)
            # - RAW_DATA: ImagingDataset -> FileSet
            # - RECONSTRUCTED: ImagingDataset -> FileSet
            # - ANALYSIS: ImagingDataset -> FileSet

            # Relationship: ImagingDataset uses InstrumentRecord metadata
            relationships.append({
                'type': 'METADATA_SOURCE',
                'from_label': 'ImagingDataset',
                'from_match': {'path': str(file_path.parent.resolve())},
                'to_label': 'InstrumentRecord',
                'to_match': {'source_file': str(file_path.resolve())}
            })

            # Relationship: ImagingDataset derived from metadata file
            relationships.append({
                'type': 'DERIVED_FROM',
                'from_label': 'ImagingDataset',
                'from_match': {'path': str(file_path.parent.resolve())},
                'to_label': 'File',  # Built-in File node (created by SciDK)
                'to_match': {'path': str(file_path.resolve())}
            })

            # -----------------------------------------------------------------
            # STEP 6: Return Success
            # -----------------------------------------------------------------
            return {
                'status': 'success',
                'data': data,
                'nodes': nodes,
                'relationships': relationships
            }

        except Exception as e:
            # -----------------------------------------------------------------
            # Error Handling
            # -----------------------------------------------------------------
            # Always catch exceptions and return error dict
            # Never let exceptions bubble up - they crash the interpretation
            return {
                'status': 'error',
                'data': {
                    'error': f'Failed to parse format: {str(e)}',
                    'error_type': type(e).__name__,
                    'path': str(file_path)
                }
            }

    # =========================================================================
    # HELPER METHODS (Optional)
    # =========================================================================

    def _parse_format(self, lines: list) -> Dict[str, Any]:
        """
        Parse format-specific metadata structure.

        Encapsulate parsing logic in helper methods for clarity.
        Return a dict of parsed fields.
        """
        metadata = {}

        # Example: Parse key-value pairs
        for line in lines:
            if '=' in line:
                key, value = line.split('=', 1)
                metadata[key.strip()] = value.strip()

        # Example: Type conversion
        if 'voxel_size' in metadata:
            try:
                metadata['voxel_size'] = float(metadata['voxel_size'])
            except ValueError:
                pass

        return metadata


# =============================================================================
# DECISION POINT: Bio-Formats vs. Custom Implementation
# =============================================================================
"""
When to extend BioFormatsInterpreter instead of writing custom:

EXTEND BioFormatsInterpreter IF:
✅ Format is supported by Bio-Formats (check: https://bio-formats.readthedocs.io/en/stable/supported-formats.html)
✅ Format is microscopy-related (confocal, widefield, OME-TIFF, etc.)
✅ You want standardized OME-XML metadata representation
✅ You're okay depending on external bftools installation

Example: OMETiffInterpreter extends BioFormatsInterpreter

WRITE CUSTOM IMPLEMENTATION IF:
✅ Format is NOT supported by Bio-Formats
✅ Format is preclinical/specialized (microCT, ultrasound, IVIS, flow cytometry)
✅ You need vendor-specific metadata not in Bio-Formats
✅ You want no external dependencies
✅ Bio-Formats doesn't extract the metadata you need

Example: BrukerSkyScanLogInterpreter is custom

To extend Bio-Formats:
    from .bioformats_base import BioFormatsInterpreter

    class MyFormatInterpreter(BioFormatsInterpreter):
        id = "my_format"
        name = "My Format"
        extensions = [".myformat"]

        # Optionally override _infer_modality() for format-specific logic
        # Optionally enhance interpret() to add format-specific properties
"""


# =============================================================================
# MODALITY COVERAGE: What's Implemented vs. What's Needed
# =============================================================================
"""
Current Interpreter Coverage by Modality:

PRECLINICAL IMAGING (Custom Interpreters - Bio-Formats doesn't support):
  ✅ Bruker SkyScan microCT - BrukerSkyScanLogInterpreter + BrukerMicroCtDatasetInterpreter
  🔲 IVIS optical imaging - Planned (PerkinElmer .txt parameter files)
  🔲 Ultrasound - Planned (Vevo, VisualSonics vendor formats)
  🔲 Flow cytometry FCS - Planned (FCS 3.0/3.1 standard)
  🔲 Histology slide scanners - Planned (Aperio, Hamamatsu vendor formats)

MICROSCOPY (Bio-Formats Integration):
  ✅ OME-TIFF - OMETiffInterpreter (extends BioFormatsInterpreter)
  ✅ DICOM (research/microscopy) - DicomBioFormatsInterpreter (extends BioFormatsInterpreter)
  🔲 Zeiss CZI - Planned (Bio-Formats support via base class)
  🔲 Leica LIF - Planned (Bio-Formats support via base class)
  🔲 Nikon ND2 - Planned (Bio-Formats support via base class)
  🔲 Olympus VSI - Planned (Bio-Formats support via base class)

CLINICAL IMAGING:
  ✅ DICOM (basic) - Legacy interpreter in interpreters/imaging/dicom.py (pydicom)
  🔲 NIfTI neuroimaging - Planned (nibabel library)
  🔲 DICOM-RT (radiotherapy) - Planned
  🔲 PET/SPECT - Planned (via enhanced DICOM interpreter)

GENERAL IMAGING:
  ✅ TIFF (basic) - Legacy interpreter in interpreters/imaging/tiff.py
  🔲 PNG with EXIF - Planned (PIL/Pillow)
  🔲 JPEG with EXIF - Planned (PIL/Pillow)

DECISION TREE FOR NEW FORMATS:

1. Is it supported by Bio-Formats?
   YES → Extend BioFormatsInterpreter
   NO → Continue to #2

2. Is it a preclinical/specialized format?
   YES → Write custom interpreter (this template)
   NO → Continue to #3

3. Is there a Python library for it?
   YES → Use library in custom interpreter
   NO → Parse manually or call external tools

4. For composite datasets (multiple files = one dataset):
   - Use FileSet nodes to avoid graph explosion
   - See BrukerMicroCtDatasetInterpreter for pattern
   - Don't create individual File nodes for every TIFF in a stack
"""


# =============================================================================
# COMPOSITE DATASET PATTERN REFERENCE
# =============================================================================
"""
For formats where one "dataset" comprises many files (TIFF stacks, DICOM series):

Key principles:
1. Create FileSet nodes instead of individual File nodes
2. Store glob patterns, not individual file paths
3. Track workflow stages (raw, reconstructed, analysis)
4. Link all FileSets to parent ImagingDataset

Example from BrukerMicroCtDatasetInterpreter:

    # Create FileSet for raw TIFF stack
    raw_fileset_node = {
        'label': 'FileSet',
        'key_property': 'id',
        'properties': {
            'id': f"{dataset_name}_raw",
            'stage': 'raw',
            'file_count': 500,  # Number of files
            'format': 'TIFF',
            'pattern': 'dataset_*.tif',  # Glob pattern
            'path': '/path/to/dataset/',
            'first_file': 'dataset_00000001.tif',
            'last_file': 'dataset_00000500.tif'
        }
    }

    # Link to parent ImagingDataset
    relationship = {
        'type': 'RAW_DATA',
        'from_label': 'ImagingDataset',
        'from_match': {'path': '/path/to/dataset/'},
        'to_label': 'FileSet',
        'to_match': {'id': f"{dataset_name}_raw"}
    }

This prevents creating 500 individual File nodes, which would explode the graph.
"""


# =============================================================================
# CRITICAL METADATA HIERARCHY
# =============================================================================
"""
Priority of metadata to extract (most important first):

1. VOXEL/PIXEL SIZE - Absolutely critical for spatial measurements
   - Store in micrometers (um)
   - Properties: voxel_size_um, pixel_size_um
   - Without this, images can't be properly analyzed

2. DIMENSIONS - Image size
   - Format: "512x512x200" (WxHxD) or "2048x2048" (WxH)
   - Property: dimensions

3. MODALITY - Imaging technique
   - Examples: microCT, MRI, ultrasound, confocal_microscopy, IVIS
   - Property: modality
   - Used for downstream analysis routing

4. ACQUISITION DATE/TIME - Temporal tracking
   - ISO 8601 format preferred: "2025-03-01T10:30:00"
   - Property: acquisition_date

5. INSTRUMENT INFORMATION - Provenance
   - Manufacturer, model, settings
   - Properties: instrument, instrument_vendor

6. ACQUISITION PARAMETERS - Technical details
   - Modality-specific (voltage, exposure, wavelength, etc.)
   - Store in InstrumentRecord node

7. RECONSTRUCTION PARAMETERS - Processing history
   - Filter settings, reconstruction kernel
   - Important for reproducibility

If metadata is missing, document it in 'data' but don't fail interpretation.
Return partial metadata rather than erroring out.
"""


# =============================================================================
# TESTING YOUR INTERPRETER
# =============================================================================
"""
Create a test file in tests/test_my_format_interpreter.py:

from pathlib import Path
import pytest
from scidk.interpreters.my_format import MyFormatInterpreter

def test_my_format_basic(tmp_path):
    '''Test basic interpretation.'''
    interp = MyFormatInterpreter()

    # Create test file
    test_file = tmp_path / "test.myformat"
    test_file.write_text("voxel_size=10.5\\nmodality=microCT")

    result = interp.interpret(test_file)

    assert result['status'] == 'success'
    assert result['data']['voxel_size_um'] == 10.5
    assert 'nodes' in result
    assert len(result['nodes']) >= 1

def test_my_format_missing_file(tmp_path):
    '''Test error handling.'''
    interp = MyFormatInterpreter()
    nonexistent = tmp_path / "missing.myformat"

    result = interp.interpret(nonexistent)

    assert result['status'] == 'error'
    assert 'File not found' in result['data']['error']

Run tests: pytest tests/test_my_format_interpreter.py -v
"""


# =============================================================================
# REGISTRATION
# =============================================================================
"""
To register your interpreter:

1. Add import to scidk/interpreters/__init__.py:
   from .my_format import MyFormatInterpreter

2. Add to INTERPRETERS list:
   INTERPRETERS = [
       # ... existing interpreters
       MyFormatInterpreter,
   ]

3. Restart SciDK - your interpreter is now active

Auto-registration happens via:
- Extension matching (files with .myformat extension)
- Pattern rules (if needed for complex routing)
"""


# =============================================================================
# RESOURCES
# =============================================================================
"""
Reference implementations:
- Simple file-level: scidk/interpreters/bruker_skyscan_log.py
- Composite dataset: scidk/interpreters/bruker_microct_dataset.py
- Bio-Formats routing: scidk/interpreters/ome_tiff.py
- Legacy formats: interpreters/imaging/tiff.py, interpreters/imaging/dicom.py

Documentation:
- Interpreter contract: scripts/contracts/INTERPRETERS.md
- Bio-Formats setup: docs/setup/BIOFORMATS_SETUP.md
- Bruker integration: dev/BRUKER_MICROCT_INTEGRATION.md
- Bio-Formats integration: dev/BIOFORMATS_INTEGRATION.md

Questions? Consult existing interpreters - they're the authoritative examples.
"""
