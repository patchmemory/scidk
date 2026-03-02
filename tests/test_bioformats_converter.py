"""
Tests for Bio-Formats converter.

These tests verify the converter architecture without requiring actual
bftools installation. Mock tests demonstrate expected conversion behavior.
"""
from pathlib import Path
from unittest.mock import Mock, patch
import pytest

from scidk.export.bioformats_converter import BioFormatsConverter, convert_image


class TestBioFormatsConverter:
    """Test Bio-Formats converter functionality."""

    def test_supported_formats(self):
        """Test that supported formats are correctly defined."""
        converter = BioFormatsConverter()
        formats = converter.get_supported_formats()

        assert '.ome.tif' in formats
        assert '.ome.tiff' in formats
        assert '.tif' in formats
        assert '.tiff' in formats
        assert '.png' in formats
        assert '.jpg' in formats
        assert '.jpeg' in formats
        assert '.avi' in formats

        assert formats['.ome.tif'] == 'OME-TIFF'
        assert formats['.png'] == 'PNG'

    def test_convert_missing_input_file(self, tmp_path):
        """Test error handling for missing input file."""
        converter = BioFormatsConverter()
        input_file = tmp_path / "nonexistent.czi"
        output_file = tmp_path / "output.ome.tif"

        result = converter.convert(input_file, output_file)

        assert result['status'] == 'error'
        assert 'Input file not found' in result['error']

    def test_convert_unsupported_format(self, tmp_path):
        """Test error for unsupported output format."""
        converter = BioFormatsConverter()
        input_file = tmp_path / "input.czi"
        input_file.write_text("dummy")
        output_file = tmp_path / "output.xyz"  # Unsupported format

        result = converter.convert(input_file, output_file)

        assert result['status'] == 'error'
        assert 'Unsupported output format' in result['error']
        assert '.xyz' in result['error']

    def test_convert_bfconvert_not_found(self, tmp_path):
        """Test error when bfconvert tool is not installed."""
        converter = BioFormatsConverter()
        input_file = tmp_path / "input.czi"
        input_file.write_text("dummy")
        output_file = tmp_path / "output.ome.tif"

        # Mock shutil.which to return None (tool not found)
        with patch('shutil.which', return_value=None):
            result = converter.convert(input_file, output_file)

        assert result['status'] == 'error'
        assert 'bfconvert tool not found' in result['error']
        assert result['error_type'] == 'BIOFORMATS_NOT_INSTALLED'

    @patch('subprocess.run')
    @patch('shutil.which')
    def test_successful_conversion(self, mock_which, mock_run, tmp_path):
        """Test successful conversion with mocked bfconvert."""
        converter = BioFormatsConverter()
        input_file = tmp_path / "input.czi"
        input_file.write_bytes(b"dummy input data")
        output_file = tmp_path / "output.ome.tif"

        # Mock bfconvert executable found
        mock_which.return_value = '/usr/bin/bfconvert'

        # Mock successful subprocess execution
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = 'Conversion complete'
        mock_result.stderr = ''
        mock_run.return_value = mock_result

        # Create mock output file
        output_file.write_bytes(b"dummy output data")

        result = converter.convert(input_file, output_file)

        assert result['status'] == 'success'
        assert result['output_path'] == str(output_file.resolve())
        assert 'metadata' in result

        metadata = result['metadata']
        assert metadata['input_format'] == '.czi'
        assert metadata['output_format'] == 'OME-TIFF'
        assert metadata['input_size_bytes'] == len(b"dummy input data")
        assert metadata['output_size_bytes'] == len(b"dummy output data")
        assert 'duration_ms' in metadata

    @patch('subprocess.run')
    @patch('shutil.which')
    def test_conversion_with_options(self, mock_which, mock_run, tmp_path):
        """Test conversion with compression options."""
        converter = BioFormatsConverter()
        input_file = tmp_path / "input.czi"
        input_file.write_bytes(b"dummy")
        output_file = tmp_path / "output.ome.tif"

        mock_which.return_value = '/usr/bin/bfconvert'
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = ''
        mock_result.stderr = ''
        mock_run.return_value = mock_result

        output_file.write_bytes(b"converted")

        options = {'compression': 'LZW', 'series': 0}
        result = converter.convert(input_file, output_file, options=options)

        assert result['status'] == 'success'
        assert result['metadata']['options'] == options

        # Verify bfconvert was called with correct options
        call_args = mock_run.call_args[0][0]
        assert '-compression' in call_args
        assert 'LZW' in call_args
        assert '-series' in call_args
        assert '0' in call_args

    @patch('subprocess.run')
    @patch('shutil.which')
    def test_conversion_failure(self, mock_which, mock_run, tmp_path):
        """Test handling of bfconvert execution failure."""
        converter = BioFormatsConverter()
        input_file = tmp_path / "corrupt.czi"
        input_file.write_text("corrupt")
        output_file = tmp_path / "output.ome.tif"

        mock_which.return_value = '/usr/bin/bfconvert'

        # Mock failed subprocess execution
        mock_result = Mock()
        mock_result.returncode = 1
        mock_result.stdout = ''
        mock_result.stderr = 'Error: Cannot parse file format'
        mock_run.return_value = mock_result

        result = converter.convert(input_file, output_file)

        assert result['status'] == 'error'
        assert 'bfconvert failed' in result['error']
        assert result['error_type'] == 'CONVERSION_FAILED'
        assert result['returncode'] == 1

    @patch('subprocess.run')
    @patch('shutil.which')
    def test_batch_conversion(self, mock_which, mock_run, tmp_path):
        """Test batch conversion of multiple files."""
        converter = BioFormatsConverter()

        # Create input files
        input_dir = tmp_path / "inputs"
        input_dir.mkdir()
        input_files = []
        for i in range(3):
            f = input_dir / f"input_{i}.czi"
            f.write_bytes(b"dummy")
            input_files.append(f)

        output_dir = tmp_path / "outputs"

        mock_which.return_value = '/usr/bin/bfconvert'
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = ''
        mock_result.stderr = ''
        mock_run.return_value = mock_result

        # Mock output file creation
        def create_output(*args, **kwargs):
            # Extract output path from command
            cmd = args[0]
            output_path = Path(cmd[-1])
            output_path.write_bytes(b"converted")
            return mock_result

        mock_run.side_effect = create_output

        result = converter.batch_convert(input_files, output_dir, '.ome.tif')

        assert result['status'] == 'success'
        assert result['total'] == 3
        assert result['successful'] == 3
        assert result['failed'] == 0
        assert len(result['conversions']) == 3

    def test_is_available_not_installed(self):
        """Test is_available returns False when bfconvert not found."""
        converter = BioFormatsConverter()

        with patch('shutil.which', return_value=None):
            assert converter.is_available() is False

    def test_is_available_installed(self):
        """Test is_available returns True when bfconvert is found."""
        converter = BioFormatsConverter()

        with patch('shutil.which', return_value='/usr/bin/bfconvert'):
            assert converter.is_available() is True

    @patch('subprocess.run')
    @patch('shutil.which')
    def test_convenience_function(self, mock_which, mock_run, tmp_path):
        """Test convenience convert_image function."""
        input_file = tmp_path / "input.czi"
        input_file.write_bytes(b"dummy")
        output_file = tmp_path / "output.ome.tif"

        mock_which.return_value = '/usr/bin/bfconvert'
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = ''
        mock_result.stderr = ''
        mock_run.return_value = mock_result

        output_file.write_bytes(b"converted")

        result = convert_image(
            str(input_file),
            str(output_file),
            compression='LZW'
        )

        assert result['status'] == 'success'
        assert result['metadata']['options']['compression'] == 'LZW'


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
