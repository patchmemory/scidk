# Interpreter Contract

## Purpose

Interpreters take a file path and return metadata about that file. They enable SciDK to understand and extract information from various file formats (CSV, JSON, YAML, images, scientific data files, etc.).

## Class-Based Format (Current Standard)

**All built-in interpreters use class-based format.** This is the authoritative pattern as of 2025.

```python
class MyInterpreter:
    id = "my_format"              # Required: unique identifier
    name = "My Format"            # Required: human-readable name
    version = "1.0.0"             # Required: semantic version
    extensions = [".ext"]         # Required: file extensions
    default_enabled = True        # Optional: default enablement state

    def interpret(self, file_path: Path) -> Dict:
        """
        Interpret a file and return metadata.

        Args:
            file_path: Path to file to interpret

        Returns:
            Dict with 'status' and 'data' keys
        """
        # Implementation here
```

**Template**: See `scidk/interpreters/TEMPLATE_imaging.py` for comprehensive guidance.

## Function-Based Format (Deprecated)

> ⚠️ **DEPRECATED**: The function-based format with YAML frontmatter is legacy.
> All new interpreters should use class-based format above.

The original contract allowed standalone functions:

```python
def interpret(file_path: Path) -> Dict:
    """Interpret a file and return metadata."""
```

This format is still supported for backward compatibility but is not recommended.

## Return Type

### Basic Return Structure (Required)

```python
{
    'status': 'success' | 'error',
    'data': {
        # For success: metadata about the file
        'type': str,           # File type (csv, json, image, etc.)
        'row_count': int,      # Optional: number of rows/records
        'column_count': int,   # Optional: number of columns/fields
        # ... any other metadata

        # For error: error details
        'error': str,          # Error message
        'path': str            # Path that failed
    }
}
```

### Extended Return Structure (Optional - for graph integration)

Imaging and scientific data interpreters can declare Neo4j graph nodes and relationships:

```python
{
    'status': 'success',
    'data': {
        # Your extracted metadata
    },
    'nodes': [
        {
            'label': 'ImagingDataset',     # Node label in Neo4j
            'key_property': 'path',        # Unique identifier property
            'properties': {
                'path': '/path/to/dataset',
                'modality': 'microCT',
                'voxel_size_um': 10.5,
                # ... other properties
            }
        },
        # ... more nodes
    ],
    'relationships': [
        {
            'type': 'METADATA_SOURCE',           # Relationship type
            'from_label': 'ImagingDataset',      # Source node label
            'from_match': {'path': '/dataset'},  # How to find source
            'to_label': 'InstrumentRecord',      # Target node label
            'to_match': {'source_file': '/file'} # How to find target
        },
        # ... more relationships
    ]
}
```

See `scidk/interpreters/bruker_skyscan_log.py` or `scidk/interpreters/ome_tiff.py` for examples.

## Contract Tests

Your interpreter will be tested against these requirements:

1. ✅ **Has interpret() function** - Must define a function named `interpret`
2. ✅ **Accepts Path parameter** - Function must accept at least one parameter (file_path)
3. ✅ **Returns dict** - Must return a dictionary object
4. ✅ **Returns 'status' key** - Dict must contain a 'status' key
5. ✅ **Handles missing file** - Must return `{'status': 'error', 'data': {...}}` for non-existent files
6. ✅ **Handles corrupt file** - Must return `{'status': 'error', 'data': {...}}` or handle gracefully
7. ✅ **Handles empty file** - Must return `{'status': 'success', 'data': {...}}` with appropriate metadata

## Example Implementation (Class-Based)

```python
from pathlib import Path
from typing import Dict
import csv

class CsvInterpreter:
    id = "csv"
    name = "CSV Interpreter"
    version = "1.0.0"
    extensions = [".csv"]
    default_enabled = True

    def interpret(self, file_path: Path) -> Dict:
        """Interpret a CSV file."""

        # Handle missing file
        if not file_path.exists():
            return {
                'status': 'error',
                'data': {
                    'error': 'File not found',
                    'path': str(file_path)
                }
            }

        # Try to read CSV
        try:
            with open(file_path, 'r') as f:
                reader = csv.reader(f)
                rows = list(reader)

                # Handle empty file
                if len(rows) == 0:
                    return {
                        'status': 'success',
                        'data': {
                            'type': 'csv',
                            'row_count': 0,
                            'headers': []
                        }
                    }

                # Normal case
                return {
                    'status': 'success',
                    'data': {
                        'type': 'csv',
                        'row_count': len(rows) - 1,
                        'headers': rows[0],
                        'column_count': len(rows[0])
                    }
                }

        except Exception as e:
            return {
                'status': 'error',
                'data': {
                    'error': f'Failed to parse CSV: {str(e)}',
                    'path': str(file_path)
                }
            }
```

See `scidk/interpreters/TEMPLATE_imaging.py` for a comprehensive template with detailed inline guidance.

## Best Practices

1. **Always check if file exists** before opening
2. **Handle exceptions gracefully** - return error status, don't crash
3. **Return consistent structure** - always include 'status' and 'data'
4. **Be efficient** - don't load entire large files into memory
5. **Document your output** - explain what metadata fields mean
6. **Use type hints** - helps users understand your interface

## Common Pitfalls

❌ **Don't crash on missing files**
```python
def interpret(file_path: Path) -> Dict:
    with open(file_path) as f:  # Will crash if file doesn't exist!
```

❌ **Don't return inconsistent types**
```python
# Bad: returns string on error, dict on success
return "Error: file not found"
```

❌ **Don't forget the 'status' key**
```python
# Bad: no status key
return {'data': {...}}
```

## Integration

Once validated, your interpreter will:
- Appear in **File Settings** → Interpreter dropdown
- Be available for selection when configuring file scanning
- Run automatically on matching file extensions
- Show results in Files page and graph commits

## Testing Your Interpreter

Before validation, test manually with:

```python
from pathlib import Path
from my_interpreter import interpret

# Test cases
test_files = [
    Path('/path/to/valid.csv'),
    Path('/nonexistent/file.txt'),  # Should return error
    Path('/path/to/empty.csv'),     # Should handle gracefully
]

for file in test_files:
    result = interpret(file)
    print(f"{file.name}: {result['status']}")
    if result['status'] == 'error':
        print(f"  Error: {result['data']['error']}")
```

## Validation Process

1. Click "Validate" in Scripts page
2. Sandbox runs your code with test inputs
3. Contract tests check all requirements
4. If passed: ✅ **Validated** → Available in Settings
5. If failed: ❌ **Failed** → See errors, fix and retry

## Bio-Formats vs. Custom Implementation

When adding support for a new imaging format, decide whether to extend `BioFormatsInterpreter` or write a custom implementation:

### Extend BioFormatsInterpreter IF:

✅ Format is supported by Bio-Formats ([supported formats list](https://bio-formats.readthedocs.io/en/stable/supported-formats.html))
✅ Format is microscopy-related (confocal, widefield, OME-TIFF, etc.)
✅ You want standardized OME-XML metadata representation
✅ You're okay depending on external bftools installation

**Example**: `OMETiffInterpreter` extends `BioFormatsInterpreter`

### Write Custom Implementation IF:

✅ Format is NOT supported by Bio-Formats
✅ Format is preclinical/specialized (microCT, ultrasound, IVIS, flow cytometry)
✅ You need vendor-specific metadata not in Bio-Formats
✅ You want no external dependencies
✅ Bio-Formats doesn't extract the metadata you need

**Example**: `BrukerSkyScanLogInterpreter` is custom

### To extend Bio-Formats:

```python
from scidk.interpreters.bioformats_base import BioFormatsInterpreter

class MyFormatInterpreter(BioFormatsInterpreter):
    id = "my_format"
    name = "My Format Interpreter"
    version = "1.0.0"
    extensions = [".myformat"]

    # Optionally override _infer_modality() for format-specific logic
    # Optionally enhance interpret() to add format-specific properties
```

See `docs/setup/BIOFORMATS_SETUP.md` for Bio-Formats installation and usage.

## Modality Coverage

Current interpreter coverage by imaging modality:

### Preclinical Imaging (Custom Interpreters)
- ✅ **Bruker SkyScan microCT** - `BrukerSkyScanLogInterpreter`, `BrukerMicroCtDatasetInterpreter`
- 🔲 **IVIS optical imaging** - Planned (Bio-Formats doesn't support)
- 🔲 **Ultrasound** - Planned (vendor-specific formats)
- 🔲 **Flow cytometry FCS** - Planned (FCS standard, not in Bio-Formats)
- 🔲 **Histology slide scanners** - Planned (vendor-specific)

### Microscopy (Bio-Formats Integration)
- ✅ **OME-TIFF** - `OMETiffInterpreter` (extends `BioFormatsInterpreter`)
- ✅ **DICOM (research/microscopy)** - `DicomBioFormatsInterpreter` (extends `BioFormatsInterpreter`)
- 🔲 **Zeiss CZI** - Planned (Bio-Formats support)
- 🔲 **Leica LIF** - Planned (Bio-Formats support)
- 🔲 **Nikon ND2** - Planned (Bio-Formats support)

### Clinical Imaging
- ✅ **DICOM (basic)** - Legacy interpreter in `interpreters/imaging/dicom.py`
- 🔲 **NIfTI neuroimaging** - Planned
- 🔲 **DICOM-RT** - Planned

### General Imaging
- ✅ **TIFF (basic)** - Legacy interpreter in `interpreters/imaging/tiff.py`
- 🔲 **PNG with EXIF** - Planned
- 🔲 **JPEG with EXIF** - Planned

## Registration

To register your interpreter:

1. **Add import** to `scidk/interpreters/__init__.py`:
   ```python
   from .my_format import MyFormatInterpreter
   ```

2. **Add to INTERPRETERS list**:
   ```python
   INTERPRETERS = [
       # ... existing interpreters
       MyFormatInterpreter,
   ]
   ```

3. **Restart SciDK** - your interpreter is now active

Auto-registration happens via:
- Extension matching (files with your declared extensions)
- Pattern rules (if needed for complex routing)

## Resources

**Templates and Examples:**
- Comprehensive template: `scidk/interpreters/TEMPLATE_imaging.py`
- Simple file-level: `scidk/interpreters/bruker_skyscan_log.py`
- Composite dataset: `scidk/interpreters/bruker_microct_dataset.py`
- Bio-Formats routing: `scidk/interpreters/ome_tiff.py`
- Legacy formats: `interpreters/imaging/tiff.py`, `interpreters/imaging/dicom.py`

**Documentation:**
- Bio-Formats setup: `docs/setup/BIOFORMATS_SETUP.md`
- Bruker integration: `dev/BRUKER_MICROCT_INTEGRATION.md`
- Bio-Formats integration: `dev/BIOFORMATS_INTEGRATION.md`

**Tests:**
- Sample validation: `tests/fixtures/script_validation/sample_csv_interpreter.py`
- Bio-Formats tests: `tests/test_bioformats_interpreters.py`
- Converter tests: `tests/test_bioformats_converter.py`
