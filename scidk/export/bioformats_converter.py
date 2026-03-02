"""
Bio-Formats Converter

Provides file format conversion using Bio-Formats bfconvert command line tool.
This is a stub implementation demonstrating the conversion pathway architecture.

For demo purposes: shows how conversion would be integrated, but not yet
connected to UI workflows or batch processing infrastructure.
"""
from pathlib import Path
from typing import Dict, Any, Optional, List
import subprocess
import shutil


class BioFormatsConverter:
    """
    Wrapper for Bio-Formats bfconvert command line tool.

    Provides format conversion for microscopy and imaging files supported
    by Bio-Formats. This is an architectural stub demonstrating the conversion
    pathway - full production integration would include:
    - UI integration for conversion requests
    - Batch processing queue
    - Progress tracking
    - Neo4j relationship tracking (converted files → source files)

    Supported output formats:
    - OME-TIFF (.ome.tif, .ome.tiff)
    - TIFF (.tif, .tiff)
    - PNG (.png)
    - JPEG (.jpg, .jpeg)
    - AVI (.avi) for time series
    """

    # Supported output format extensions
    SUPPORTED_FORMATS = {
        '.ome.tif': 'OME-TIFF',
        '.ome.tiff': 'OME-TIFF',
        '.tif': 'TIFF',
        '.tiff': 'TIFF',
        '.png': 'PNG',
        '.jpg': 'JPEG',
        '.jpeg': 'JPEG',
        '.avi': 'AVI',
    }

    def __init__(self):
        self._bfconvert_path = None

    def convert(
        self,
        input_path: Path,
        output_path: Path,
        options: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Convert an image file to a different format using bfconvert.

        Args:
            input_path: Path to input file
            output_path: Path for output file (extension determines format)
            options: Optional conversion options (e.g., compression, series selection)

        Returns:
            Dict with:
            - status: 'success' or 'error'
            - output_path: Path to converted file (if success)
            - error: Error message (if error)
            - metadata: Conversion metadata (duration, file sizes, etc.)

        Example:
            converter = BioFormatsConverter()
            result = converter.convert(
                Path('input.czi'),
                Path('output.ome.tif'),
                options={'compression': 'LZW', 'series': 0}
            )
        """
        if not input_path.exists():
            return {
                'status': 'error',
                'error': f'Input file not found: {input_path}'
            }

        # Check output format is supported
        # Handle compound extensions like .ome.tif
        output_ext = self._get_extension(output_path)
        if output_ext not in self.SUPPORTED_FORMATS:
            return {
                'status': 'error',
                'error': f'Unsupported output format: {output_ext}. Supported: {", ".join(self.SUPPORTED_FORMATS.keys())}'
            }

        # Find bfconvert executable
        bfconvert_path = self._find_bfconvert()
        if not bfconvert_path:
            return {
                'status': 'error',
                'error': 'Bio-Formats bfconvert tool not found. Install with: conda install ome::bftools',
                'error_type': 'BIOFORMATS_NOT_INSTALLED'
            }

        try:
            # Build bfconvert command
            cmd = [bfconvert_path]

            # Add options
            options = options or {}

            # Compression option
            if 'compression' in options:
                cmd.extend(['-compression', str(options['compression'])])

            # Series selection (for multi-series files)
            if 'series' in options:
                cmd.extend(['-series', str(options['series'])])

            # No upgrade check (faster)
            cmd.append('-no-upgrade')

            # Input and output paths
            cmd.extend([str(input_path), str(output_path)])

            # Track start time
            import time
            start_time = time.time()

            # Run bfconvert
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300  # 5 minute timeout for conversion
            )

            # Track duration
            duration_ms = int((time.time() - start_time) * 1000)

            if result.returncode != 0:
                return {
                    'status': 'error',
                    'error': f'bfconvert failed: {result.stderr}',
                    'error_type': 'CONVERSION_FAILED',
                    'returncode': result.returncode,
                    'duration_ms': duration_ms
                }

            # Verify output file was created
            if not output_path.exists():
                return {
                    'status': 'error',
                    'error': 'bfconvert completed but output file not found',
                    'error_type': 'OUTPUT_NOT_CREATED',
                    'duration_ms': duration_ms
                }

            # Get file sizes
            input_size = input_path.stat().st_size
            output_size = output_path.stat().st_size

            return {
                'status': 'success',
                'output_path': str(output_path.resolve()),
                'metadata': {
                    'input_format': input_path.suffix,
                    'output_format': self.SUPPORTED_FORMATS[output_ext],
                    'input_size_bytes': input_size,
                    'output_size_bytes': output_size,
                    'compression_ratio': round(output_size / input_size, 2) if input_size > 0 else None,
                    'duration_ms': duration_ms,
                    'options': options
                }
            }

        except subprocess.TimeoutExpired:
            return {
                'status': 'error',
                'error': 'Conversion timed out (>5 minutes)',
                'error_type': 'TIMEOUT'
            }
        except Exception as e:
            return {
                'status': 'error',
                'error': f'Conversion failed: {str(e)}',
                'error_type': type(e).__name__
            }

    def batch_convert(
        self,
        input_paths: List[Path],
        output_dir: Path,
        output_format: str,
        options: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Convert multiple files to the same output format.

        This is a stub for batch conversion functionality. In production,
        this would integrate with a job queue system for parallel processing.

        Args:
            input_paths: List of input file paths
            output_dir: Directory for output files
            output_format: Output format extension (e.g., '.ome.tif')
            options: Conversion options applied to all files

        Returns:
            Dict with batch conversion results
        """
        if not output_dir.exists():
            output_dir.mkdir(parents=True, exist_ok=True)

        results = {
            'status': 'success',
            'total': len(input_paths),
            'successful': 0,
            'failed': 0,
            'conversions': []
        }

        for input_path in input_paths:
            # Generate output filename
            output_filename = input_path.stem + output_format
            output_path = output_dir / output_filename

            # Convert
            conv_result = self.convert(input_path, output_path, options)

            # Track result
            results['conversions'].append({
                'input': str(input_path),
                'output': str(output_path) if conv_result['status'] == 'success' else None,
                'status': conv_result['status'],
                'error': conv_result.get('error')
            })

            if conv_result['status'] == 'success':
                results['successful'] += 1
            else:
                results['failed'] += 1

        # Overall status
        if results['failed'] > 0:
            results['status'] = 'partial' if results['successful'] > 0 else 'error'

        return results

    def get_supported_formats(self) -> Dict[str, str]:
        """
        Get dictionary of supported output formats.

        Returns:
            Dict mapping file extension to format name
        """
        return self.SUPPORTED_FORMATS.copy()

    def is_available(self) -> bool:
        """
        Check if bfconvert tool is available.

        Returns:
            True if bfconvert is found, False otherwise
        """
        return self._find_bfconvert() is not None

    def _get_extension(self, path: Path) -> str:
        """
        Get file extension, handling compound extensions like .ome.tif.

        Args:
            path: Path object

        Returns:
            Extension string (e.g., '.ome.tif', '.tif', '.png')
        """
        name_lower = path.name.lower()

        # Check for compound extensions first
        for ext in ['.ome.tif', '.ome.tiff']:
            if name_lower.endswith(ext):
                return ext

        # Otherwise return single extension
        return path.suffix.lower()

    def _find_bfconvert(self) -> Optional[str]:
        """Find bfconvert executable in PATH or common locations."""
        if self._bfconvert_path:
            return self._bfconvert_path

        # Check if bfconvert is in PATH
        path = shutil.which('bfconvert')
        if path:
            self._bfconvert_path = path
            return path

        # Check common conda location
        home = Path.home()
        conda_paths = [
            home / 'miniconda3' / 'bin' / 'bfconvert',
            home / 'anaconda3' / 'bin' / 'bfconvert',
            Path('/opt/conda/bin/bfconvert'),
            Path('/usr/local/bin/bfconvert'),
        ]

        for conda_path in conda_paths:
            if conda_path.exists():
                self._bfconvert_path = str(conda_path)
                return str(conda_path)

        return None


# Convenience function for one-off conversions
def convert_image(
    input_path: str,
    output_path: str,
    **options
) -> Dict[str, Any]:
    """
    Convenience function for converting a single image file.

    Args:
        input_path: Path to input file
        output_path: Path for output file
        **options: Conversion options (compression, series, etc.)

    Returns:
        Conversion result dict

    Example:
        result = convert_image(
            'input.czi',
            'output.ome.tif',
            compression='LZW'
        )
    """
    converter = BioFormatsConverter()
    return converter.convert(
        Path(input_path),
        Path(output_path),
        options=options if options else None
    )
