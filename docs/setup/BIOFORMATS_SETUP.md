# Bio-Formats Setup Guide

## Overview

SciDK integrates with Bio-Formats command line tools (`showinf` and `bfconvert`) to interpret and convert microscopy imaging formats. This guide covers installation and verification of Bio-Formats tools.

## What is Bio-Formats?

Bio-Formats is an open-source library and toolset from the Open Microscopy Environment (OME) that supports over 150 microscopy and imaging file formats. It's particularly strong in:

- **Microscopy formats**: Zeiss CZI, Leica LIF, Nikon ND2, Olympus VSI
- **OME-TIFF**: Open Microscopy Environment TIFF (standardized microscopy format)
- **Multi-dimensional data**: Z-stacks, time series, multi-channel images
- **Metadata extraction**: Comprehensive acquisition parameters, instrument settings

## Installation

### Option 1: Conda (Recommended)

The easiest way to install Bio-Formats command line tools:

```bash
conda install -c ome bftools
```

Or if using mamba:

```bash
mamba install -c ome bftools
```

### Option 2: Manual Download

Download from the official Bio-Formats website:

1. Visit: https://bio-formats.readthedocs.io/en/stable/users/comlinetools/
2. Download `bftools.zip`
3. Extract to a directory (e.g., `~/bftools/`)
4. Add to PATH:

```bash
# Add to ~/.bashrc or ~/.zshrc
export PATH="$HOME/bftools:$PATH"
```

5. Make scripts executable:

```bash
chmod +x ~/bftools/showinf
chmod +x ~/bftools/bfconvert
```

## Verification

After installation, verify the tools are accessible:

```bash
# Check showinf
showinf -version

# Check bfconvert
bfconvert -version
```

Expected output should show Bio-Formats version (e.g., `8.1.1` or similar).

## Usage in SciDK

### Automatic Detection

SciDK interpreters automatically detect Bio-Formats tools in:

1. System PATH
2. Common conda locations:
   - `~/miniconda3/bin/`
   - `~/anaconda3/bin/`
   - `/opt/conda/bin/`
3. `/usr/local/bin/`

### Fallback Behavior

If Bio-Formats tools are not installed:

- **OME-TIFF files**: Error returned with installation instructions
- **DICOM files**: Falls back to legacy pydicom-based interpreter (if enabled)
- **Plain TIFF files**: Uses lightweight TIFF interpreter (no Bio-Formats required)

No crashes or failures - just clear error messages guiding you to install if needed.

## Interpreters Using Bio-Formats

### 1. OME-TIFF Interpreter

**Extensions**: `.ome.tif`, `.ome.tiff`

**When to use**: OME-TIFF files from confocal microscopy, high-content screening, or any microscopy workflow that exports to OME-TIFF standard.

**What it extracts**:
- Image dimensions (X, Y, Z, channels, timepoints)
- Physical pixel/voxel sizes (micrometers)
- Channel names and wavelengths
- Acquisition date/time
- Instrument manufacturer and model
- Objective lens specifications (magnification, numerical aperture)

**Example**:
```python
from pathlib import Path
from scidk.interpreters import OMETiffInterpreter

interp = OMETiffInterpreter()
result = interp.interpret(Path('confocal_z_stack.ome.tif'))

if result['status'] == 'success':
    print(f"Dimensions: {result['data']['dimensions']}")
    print(f"Voxel size: {result['data']['raw_metadata']['physical_size_z']} µm")
    print(f"Channels: {result['data']['channels']}")
```

### 2. DICOM Bio-Formats Interpreter

**Extensions**: `.dcm`, `.dicom`

**When to use**: Research/preclinical DICOM files, multi-frame DICOM, or when you want standardized OME-XML representation of DICOM metadata.

**Note**: This interpreter is disabled by default and coexists with the legacy pydicom-based DICOM interpreter. For clinical DICOM (MRI, CT, PET), the pydicom interpreter may be more appropriate.

**What it extracts**:
- Image dimensions and slice information
- Acquisition parameters converted to OME-XML format
- Series and study identifiers
- Instrument information (when available)

### 3. Future: Vendor-Specific Formats

The Bio-Formats integration pathway enables future support for:

- Zeiss CZI (confocal microscopy)
- Leica LIF (confocal microscopy)
- Nikon ND2 (widefield/confocal)
- Olympus VSI (slide scanning)
- Many others supported by Bio-Formats

These will be added as needed, following the same architectural pattern.

## Format Conversion

### Using BioFormatsConverter

The `BioFormatsConverter` class wraps the `bfconvert` tool for format conversion:

```python
from pathlib import Path
from scidk.export import BioFormatsConverter

converter = BioFormatsConverter()

# Check if bfconvert is available
if not converter.is_available():
    print("bfconvert not installed. Install with: conda install -c ome bftools")
    exit(1)

# Convert proprietary format to OME-TIFF
result = converter.convert(
    input_path=Path('input.czi'),
    output_path=Path('output.ome.tif'),
    options={'compression': 'LZW'}
)

if result['status'] == 'success':
    print(f"Converted: {result['output_path']}")
    print(f"Output size: {result['metadata']['output_size_bytes']} bytes")
    print(f"Duration: {result['metadata']['duration_ms']} ms")
else:
    print(f"Conversion failed: {result['error']}")
```

### Supported Output Formats

- **OME-TIFF** (`.ome.tif`, `.ome.tiff`) - Recommended for archival and interoperability
- **TIFF** (`.tif`, `.tiff`) - Standard TIFF without OME-XML
- **PNG** (`.png`) - For 2D image export
- **JPEG** (`.jpg`, `.jpeg`) - For 2D image export (lossy)
- **AVI** (`.avi`) - For time-series video export

### Batch Conversion

```python
from pathlib import Path
from scidk.export import BioFormatsConverter

converter = BioFormatsConverter()

input_files = [
    Path('dataset1.czi'),
    Path('dataset2.czi'),
    Path('dataset3.czi'),
]

result = converter.batch_convert(
    input_paths=input_files,
    output_dir=Path('converted/'),
    output_format='.ome.tif',
    options={'compression': 'LZW'}
)

print(f"Converted: {result['successful']}/{result['total']}")
```

## Architecture Notes

### Why CLI Tools Instead of Python Library?

SciDK uses Bio-Formats **command line tools** (`showinf`, `bfconvert`) rather than the `python-bioformats` library because:

1. **No Java dependency**: CLI tools are standalone executables, no Java/javabridge setup required
2. **Stability**: CLI interface is stable and well-supported
3. **Portability**: Works consistently across platforms
4. **Performance**: Subprocess execution is efficient for metadata-only operations

The `python-bioformats` library requires complex Java/javabridge setup that often breaks across Python/Java versions. The CLI approach is more robust for production use.

### Custom vs. Bio-Formats Interpreters

**Custom interpreters remain for formats Bio-Formats doesn't support well:**

- ✅ **Bruker SkyScan microCT** - Custom log parser + composite dataset interpreter
- ✅ **Plain TIFF** - Lightweight interpreter (no Bio-Formats overhead)
- 🔲 **IVIS optical imaging** - Future custom interpreter (Bio-Formats doesn't support)
- 🔲 **Ultrasound** - Future custom interpreter (vendor-specific formats)
- 🔲 **Flow cytometry FCS** - Future custom interpreter (FCS standard, not in Bio-Formats)

**Bio-Formats handles standard microscopy:**

- OME-TIFF
- Zeiss CZI
- Leica LIF
- Nikon ND2
- DICOM (research/microscopy use cases)

This division leverages Bio-Formats' strengths while maintaining custom parsers for preclinical/specialized formats.

## Troubleshooting

### "showinf tool not found"

**Problem**: SciDK can't find the `showinf` executable.

**Solutions**:
1. Install bftools: `conda install -c ome bftools`
2. Verify installation: `showinf -version`
3. Check PATH: `which showinf`
4. If manual install, ensure directory is in PATH

### "bfconvert failed: Cannot read file format"

**Problem**: Bio-Formats doesn't support the input file format.

**Solutions**:
1. Check if format is supported: https://bio-formats.readthedocs.io/en/stable/supported-formats.html
2. If unsupported, check if SciDK has a custom interpreter for that format
3. Consider using vendor software to export to OME-TIFF first

### Slow OME-XML extraction

**Problem**: `showinf` takes a long time on large files.

**Explanation**: Some formats (especially proprietary microscopy formats) require significant parsing time. The `-nopix` flag used by SciDK skips pixel data reading, which helps, but metadata extraction can still be slow for complex multi-series files.

**Workaround**: For repeated interpretation of the same file, SciDK caches interpretation results.

### Conda environment issues

**Problem**: `conda install ome::bftools` fails or tools not found after install.

**Solutions**:
1. Activate your conda environment: `conda activate your_env`
2. Install with explicit channel: `conda install -c ome bftools`
3. Verify tools in conda environment: `which showinf` should show path in your env
4. If still not found, check conda bin is in PATH: `echo $PATH | grep conda`

## References

- **Bio-Formats Documentation**: https://bio-formats.readthedocs.io/
- **Supported Formats**: https://bio-formats.readthedocs.io/en/stable/supported-formats.html
- **Command Line Tools**: https://bio-formats.readthedocs.io/en/stable/users/comlinetools/
- **OME-TIFF Specification**: https://docs.openmicroscopy.org/ome-model/latest/
- **bftools conda package**: https://anaconda.org/ome/bftools

## Next Steps

After setting up Bio-Formats:

1. **Test interpretation**: Try interpreting an OME-TIFF file to verify setup
2. **Review interpreters**: See available interpreters in Settings → Interpreters
3. **Add file sources**: Configure rclone sources with imaging data
4. **Scan and interpret**: Let SciDK automatically interpret OME-TIFF files during scanning
5. **Explore conversions**: Use `BioFormatsConverter` to convert proprietary formats to OME-TIFF

For questions or issues, see the main SciDK documentation or file an issue on GitHub.
