"""Tests for Bruker MicroCT Dataset composite interpreter"""
from pathlib import Path
import pytest


def test_bruker_microct_dataset_from_log():
    """Test that the composite interpreter can interpret from a log file path."""
    from scidk.interpreters.bruker_microct_dataset import BrukerMicroCtDatasetInterpreter

    # Use the real sample data
    dataset_path = Path(__file__).parents[1] / 'dev' / 'code-imports' / 'sample-data' / 'bruker_skyscan' / '1L'
    log_file = dataset_path / '1L.log'

    if not log_file.exists():
        pytest.skip(f"Sample data not available: {log_file}")

    interp = BrukerMicroCtDatasetInterpreter()
    result = interp.interpret(log_file)

    # Verify success
    assert result['status'] == 'success', f"Failed: {result.get('data', {}).get('error')}"

    # Verify data
    data = result['data']
    assert data['dataset_id'] == '1L'
    assert data['voxel_size_um'] == 40.164
    assert data['stages']['raw'] == 556
    assert data['stages']['reconstructed'] == 315
    assert data['stages']['analysis'] == 5

    # Verify nodes
    nodes = result['nodes']
    assert len(nodes) == 5  # ImagingDataset + InstrumentRecord + 3 FileSets

    # Check ImagingDataset node
    imaging_node = next(n for n in nodes if n['label'] == 'ImagingDataset')
    assert imaging_node['key_property'] == 'path'
    assert imaging_node['properties']['modality'] == 'microCT'
    assert imaging_node['properties']['voxel_size_um'] == 40.164
    assert 'instrument' in imaging_node['properties']

    # Check InstrumentRecord node
    instrument_node = next(n for n in nodes if n['label'] == 'InstrumentRecord')
    assert instrument_node['key_property'] == 'source_file'
    assert 'voltage_kv' in instrument_node['properties']
    assert 'current_ua' in instrument_node['properties']

    # Check FileSet nodes
    filesets = [n for n in nodes if n['label'] == 'FileSet']
    assert len(filesets) == 3

    raw_fs = next(fs for fs in filesets if fs['properties']['stage'] == 'raw')
    assert raw_fs['properties']['file_count'] == 556
    assert raw_fs['properties']['format'] == 'TIFF'

    rec_fs = next(fs for fs in filesets if fs['properties']['stage'] == 'reconstructed')
    assert rec_fs['properties']['file_count'] == 315

    analysis_fs = next(fs for fs in filesets if fs['properties']['stage'] == 'analysis')
    assert analysis_fs['properties']['file_count'] == 5
    assert analysis_fs['properties']['format'] == 'NIfTI'

    # Verify relationships
    relationships = result['relationships']
    assert len(relationships) == 4

    # Check relationship types
    rel_types = {r['type'] for r in relationships}
    assert rel_types == {'METADATA_SOURCE', 'RAW_DATA', 'RECONSTRUCTED', 'ANALYSIS'}


def test_bruker_microct_dataset_from_directory():
    """Test that the composite interpreter can interpret from a directory path."""
    from scidk.interpreters.bruker_microct_dataset import BrukerMicroCtDatasetInterpreter

    dataset_path = Path(__file__).parents[1] / 'dev' / 'code-imports' / 'sample-data' / 'bruker_skyscan' / '1L'

    if not dataset_path.exists():
        pytest.skip(f"Sample data not available: {dataset_path}")

    interp = BrukerMicroCtDatasetInterpreter()
    result = interp.interpret(dataset_path)

    # Should work the same as log file path
    assert result['status'] == 'success'
    assert result['data']['dataset_id'] == '1L'
    assert len(result['nodes']) == 5


def test_bruker_microct_minimal_dataset():
    """Test interpreter on minimal dataset (log file only, no TIFF stacks)."""
    from scidk.interpreters.bruker_microct_dataset import BrukerMicroCtDatasetInterpreter
    import tempfile

    # Create minimal log file
    log_content = """[System]
SkyScan1276

[Acquisition]
Source Voltage (kV)=70
Source Current (uA)=142
Voxel size (um)=5.0
Study Date and Time=01 Jan 2024  10:00:00
"""

    with tempfile.TemporaryDirectory() as tmpdir:
        log_path = Path(tmpdir) / 'test.log'
        log_path.write_text(log_content)

        interp = BrukerMicroCtDatasetInterpreter()
        result = interp.interpret(log_path)

        assert result['status'] == 'success'
        data = result['data']
        assert data['dataset_id'] == 'test'
        assert data['voxel_size_um'] == 5.0
        assert data['stages']['raw'] == 0  # No TIFF files

        # Should still create ImagingDataset and InstrumentRecord
        nodes = result['nodes']
        assert len(nodes) >= 2
        labels = {n['label'] for n in nodes}
        assert 'ImagingDataset' in labels
        assert 'InstrumentRecord' in labels


def test_bruker_microct_no_log_file():
    """Test error handling when no log file found."""
    from scidk.interpreters.bruker_microct_dataset import BrukerMicroCtDatasetInterpreter
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        empty_dir = Path(tmpdir)

        interp = BrukerMicroCtDatasetInterpreter()
        result = interp.interpret(empty_dir)

        assert result['status'] == 'error'
        assert 'No acquisition .log file' in result['data']['error']


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
