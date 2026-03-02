"""
Tests for Bio-Formats interpreters.

These tests verify the architecture and behavior of Bio-Formats-based
interpreters without requiring actual bftools installation. Mock tests
demonstrate the expected behavior when bftools is available.
"""
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
import pytest

from scidk.interpreters.bioformats_base import BioFormatsInterpreter
from scidk.interpreters.ome_tiff import OMETiffInterpreter
from scidk.interpreters.dicom_bioformats import DicomBioFormatsInterpreter


# Sample OME-XML for testing
SAMPLE_OME_XML = """<?xml version="1.0" encoding="UTF-8"?>
<OME xmlns="http://www.openmicroscopy.org/Schemas/OME/2016-06"
     xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
     xsi:schemaLocation="http://www.openmicroscopy.org/Schemas/OME/2016-06 http://www.openmicroscopy.org/Schemas/OME/2016-06/ome.xsd">
    <Image ID="Image:0" Name="test_image.ome.tif">
        <AcquisitionDate>2025-03-01T10:30:00</AcquisitionDate>
        <Pixels ID="Pixels:0"
                Type="uint16"
                SizeX="512"
                SizeY="512"
                SizeZ="10"
                SizeC="3"
                SizeT="5"
                PhysicalSizeX="0.65"
                PhysicalSizeY="0.65"
                PhysicalSizeZ="2.0">
            <Channel ID="Channel:0:0" Name="DAPI" />
            <Channel ID="Channel:0:1" Name="FITC" />
            <Channel ID="Channel:0:2" Name="TRITC" />
        </Pixels>
    </Image>
    <Instrument ID="Instrument:0">
        <Microscope Manufacturer="Zeiss" Model="LSM 880" />
        <Objective ID="Objective:0" Model="Plan-Apochromat 63x" NominalMagnification="63.0" LensNA="1.4" />
    </Instrument>
</OME>
"""


class TestBioFormatsInterpreter:
    """Test base Bio-Formats interpreter functionality."""

    def test_interpreter_metadata(self):
        """Test interpreter class attributes."""
        interp = BioFormatsInterpreter()
        assert interp.id == "bioformats_base"
        assert interp.name == "Bio-Formats Base"
        assert interp.version == "1.0.0"
        assert interp.extensions == []
        assert interp.default_enabled is True

    def test_missing_file_error(self, tmp_path):
        """Test error handling for missing files."""
        interp = BioFormatsInterpreter()
        nonexistent = tmp_path / "nonexistent.tif"

        result = interp.interpret(nonexistent)

        assert result['status'] == 'error'
        assert 'File not found' in result['data']['error']
        assert str(nonexistent) in result['data']['path']

    def test_showinf_not_found(self, tmp_path):
        """Test error when showinf tool is not installed."""
        interp = BioFormatsInterpreter()
        test_file = tmp_path / "test.tif"
        test_file.write_text("dummy")

        # Mock shutil.which to return None (tool not found)
        with patch('shutil.which', return_value=None):
            result = interp.interpret(test_file)

        assert result['status'] == 'error'
        assert 'showinf tool not found' in result['data']['error']
        assert result['data']['error_type'] == 'BIOFORMATS_NOT_INSTALLED'

    @patch('subprocess.run')
    @patch('shutil.which')
    def test_successful_interpretation(self, mock_which, mock_run, tmp_path):
        """Test successful interpretation with mocked showinf."""
        # Setup
        interp = BioFormatsInterpreter()
        test_file = tmp_path / "test.ome.tif"
        test_file.write_text("dummy")

        # Mock showinf executable found
        mock_which.return_value = '/usr/bin/showinf'

        # Mock subprocess result with sample OME-XML
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = SAMPLE_OME_XML
        mock_result.stderr = ''
        mock_run.return_value = mock_result

        # Execute
        result = interp.interpret(test_file)

        # Verify
        assert result['status'] == 'success'
        assert 'data' in result
        assert 'nodes' in result
        assert 'relationships' in result

        # Check data
        data = result['data']
        assert data['channels'] == 3
        assert data['timepoints'] == 5
        assert data['z_slices'] == 10

        # Check nodes
        nodes = result['nodes']
        assert len(nodes) == 2
        imaging_node = next(n for n in nodes if n['label'] == 'ImagingDataset')
        instrument_node = next(n for n in nodes if n['label'] == 'InstrumentRecord')

        # Check ImagingDataset properties
        imaging_props = imaging_node['properties']
        assert imaging_props['path'] == str(test_file.resolve())
        assert imaging_props['dimensions'] == '512x512x10'
        assert imaging_props['channels'] == 3
        assert imaging_props['timepoints'] == 5
        assert imaging_props['pixel_size_um']['x'] == 0.65
        assert imaging_props['pixel_size_um']['y'] == 0.65
        assert imaging_props['voxel_size_um'] == 2.0
        assert imaging_props['acquisition_date'] == '2025-03-01T10:30:00'

        # Check InstrumentRecord properties
        instrument_props = instrument_node['properties']
        assert instrument_props['manufacturer'] == 'Zeiss'
        assert instrument_props['model'] == 'LSM 880'
        assert instrument_props['objective'] == 'Plan-Apochromat 63x'
        assert instrument_props['magnification'] == 63.0
        assert instrument_props['numerical_aperture'] == 1.4

        # Check relationships
        rels = result['relationships']
        assert len(rels) == 1
        assert rels[0]['type'] == 'METADATA_SOURCE'
        assert rels[0]['from_label'] == 'ImagingDataset'
        assert rels[0]['to_label'] == 'InstrumentRecord'

    @patch('subprocess.run')
    @patch('shutil.which')
    def test_showinf_execution_error(self, mock_which, mock_run, tmp_path):
        """Test handling of showinf execution errors."""
        interp = BioFormatsInterpreter()
        test_file = tmp_path / "corrupt.tif"
        test_file.write_text("corrupt data")

        mock_which.return_value = '/usr/bin/showinf'

        # Mock failed subprocess execution
        mock_result = Mock()
        mock_result.returncode = 1
        mock_result.stdout = ''
        mock_result.stderr = 'Error: Cannot read file format'
        mock_run.return_value = mock_result

        result = interp.interpret(test_file)

        assert result['status'] == 'error'
        assert 'showinf failed' in result['data']['error']
        assert result['data']['error_type'] == 'BIOFORMATS_EXECUTION_ERROR'
        assert result['data']['returncode'] == 1

    def test_parse_ome_xml_metadata(self):
        """Test OME-XML parsing extracts correct metadata."""
        interp = BioFormatsInterpreter()
        metadata = interp._parse_ome_xml(SAMPLE_OME_XML)

        # Note: Image Name attribute is not currently extracted
        assert metadata['acquisition_date'] == '2025-03-01T10:30:00'
        assert metadata['size_x'] == 512
        assert metadata['size_y'] == 512
        assert metadata['size_z'] == 10
        assert metadata['size_c'] == 3
        assert metadata['size_t'] == 5
        assert metadata['physical_size_x'] == 0.65
        assert metadata['physical_size_y'] == 0.65
        assert metadata['physical_size_z'] == 2.0
        assert metadata['channel_names'] == ['DAPI', 'FITC', 'TRITC']
        assert metadata['instrument_manufacturer'] == 'Zeiss'
        assert metadata['instrument_model'] == 'LSM 880'
        assert metadata['objective_model'] == 'Plan-Apochromat 63x'
        assert metadata['objective_magnification'] == 63.0
        assert metadata['objective_na'] == 1.4


class TestOMETiffInterpreter:
    """Test OME-TIFF specific interpreter."""

    def test_interpreter_metadata(self):
        """Test OME-TIFF interpreter attributes."""
        interp = OMETiffInterpreter()
        assert interp.id == "ome_tiff"
        assert interp.name == "OME-TIFF Interpreter"
        assert interp.version == "1.0.0"
        assert interp.extensions == [".ome.tif", ".ome.tiff"]
        assert interp.default_enabled is True

    @patch('subprocess.run')
    @patch('shutil.which')
    def test_ome_tiff_format_labeling(self, mock_which, mock_run, tmp_path):
        """Test that OME-TIFF files are labeled with correct format."""
        interp = OMETiffInterpreter()
        test_file = tmp_path / "test.ome.tif"
        test_file.write_text("dummy")

        mock_which.return_value = '/usr/bin/showinf'
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = SAMPLE_OME_XML
        mock_result.stderr = ''
        mock_run.return_value = mock_result

        result = interp.interpret(test_file)

        assert result['status'] == 'success'
        assert result['data']['format'] == 'OME-TIFF'

        # Check that ImagingDataset node has OME-TIFF format
        imaging_node = next(n for n in result['nodes'] if n['label'] == 'ImagingDataset')
        assert imaging_node['properties']['format'] == 'OME-TIFF'

    def test_modality_inference_multichannel(self):
        """Test modality inference for multi-channel OME-TIFF."""
        interp = OMETiffInterpreter()
        metadata = {'size_c': 3, 'size_z': 1, 'size_t': 1}
        modality = interp._infer_modality(metadata)
        assert modality == 'fluorescence_microscopy'

    def test_modality_inference_3d(self):
        """Test modality inference for 3D OME-TIFF."""
        interp = OMETiffInterpreter()
        metadata = {'size_c': 1, 'size_z': 50, 'size_t': 1}
        modality = interp._infer_modality(metadata)
        assert modality == '3d_microscopy'

    def test_modality_inference_timelapse(self):
        """Test modality inference for time-lapse OME-TIFF."""
        interp = OMETiffInterpreter()
        metadata = {'size_c': 1, 'size_z': 1, 'size_t': 100}
        modality = interp._infer_modality(metadata)
        assert modality == 'timelapse_microscopy'


class TestDicomBioFormatsInterpreter:
    """Test DICOM Bio-Formats interpreter."""

    def test_interpreter_metadata(self):
        """Test DICOM interpreter attributes."""
        interp = DicomBioFormatsInterpreter()
        assert interp.id == "dicom_bioformats"
        assert interp.name == "DICOM Bio-Formats Interpreter"
        assert interp.version == "1.0.0"
        assert interp.extensions == [".dcm", ".dicom"]
        assert interp.default_enabled is False  # Coexists with legacy

    @patch('subprocess.run')
    @patch('shutil.which')
    def test_dicom_format_labeling(self, mock_which, mock_run, tmp_path):
        """Test that DICOM files are labeled with correct format."""
        interp = DicomBioFormatsInterpreter()
        test_file = tmp_path / "test.dcm"
        test_file.write_text("dummy")

        mock_which.return_value = '/usr/bin/showinf'
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = SAMPLE_OME_XML  # Bio-Formats converts DICOM to OME-XML
        mock_result.stderr = ''
        mock_run.return_value = mock_result

        result = interp.interpret(test_file)

        assert result['status'] == 'success'
        assert result['data']['format'] == 'DICOM'

        # Check that ImagingDataset node has DICOM format
        imaging_node = next(n for n in result['nodes'] if n['label'] == 'ImagingDataset')
        assert imaging_node['properties']['format'] == 'DICOM'

    def test_modality_inference_dynamic(self):
        """Test modality inference for dynamic DICOM."""
        interp = DicomBioFormatsInterpreter()
        metadata = {'size_t': 20}
        modality = interp._infer_modality(metadata)
        assert modality == 'dynamic_imaging'

    def test_modality_inference_volumetric(self):
        """Test modality inference for volumetric DICOM."""
        interp = DicomBioFormatsInterpreter()
        metadata = {'size_z': 100}
        modality = interp._infer_modality(metadata)
        assert modality == 'volumetric_imaging'

    def test_modality_inference_default(self):
        """Test default modality for DICOM."""
        interp = DicomBioFormatsInterpreter()
        metadata = {}
        modality = interp._infer_modality(metadata)
        assert modality == 'medical_imaging'


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
