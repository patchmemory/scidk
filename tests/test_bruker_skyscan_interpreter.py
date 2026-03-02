"""Tests for Bruker SkyScan .log interpreter"""
from pathlib import Path
import pytest


def test_bruker_skyscan_log_parsing():
    """Test that Bruker SkyScan .log interpreter parses fixture and declares nodes."""
    from scidk.interpreters.bruker_skyscan_log import BrukerSkyScanLogInterpreter

    # Get fixture path
    fixture_path = Path(__file__).parent / 'fixtures' / 'imaging' / 'bruker_skyscan_sample.log'
    assert fixture_path.exists(), f"Fixture not found: {fixture_path}"

    # Create interpreter and run
    interp = BrukerSkyScanLogInterpreter()
    result = interp.interpret(fixture_path)

    # Verify status
    assert result['status'] == 'success', f"Interpretation failed: {result.get('data', {}).get('error')}"

    # Verify data was parsed
    data = result.get('data', {})
    assert 'imaging_properties' in data
    assert 'instrument_properties' in data
    assert data['imaging_properties'].get('voxel_size_um') == 5.0
    assert data['instrument_properties'].get('voltage_kv') == 70.0
    assert data['instrument_properties'].get('current_ua') == 142.0

    # Verify nodes were declared
    nodes = result.get('nodes', [])
    assert len(nodes) == 2, f"Expected 2 nodes, got {len(nodes)}"

    # Check ImagingDataset node
    imaging_node = next((n for n in nodes if n['label'] == 'ImagingDataset'), None)
    assert imaging_node is not None, "ImagingDataset node not declared"
    assert imaging_node['key_property'] == 'path'
    assert 'path' in imaging_node['properties']
    assert imaging_node['properties']['modality'] == 'microCT'
    assert imaging_node['properties']['voxel_size_um'] == 5.0

    # Check InstrumentRecord node
    instrument_node = next((n for n in nodes if n['label'] == 'InstrumentRecord'), None)
    assert instrument_node is not None, "InstrumentRecord node not declared"
    assert instrument_node['key_property'] == 'source_file'
    assert 'source_file' in instrument_node['properties']
    assert instrument_node['properties']['voltage_kv'] == 70.0

    # Verify relationships were declared
    relationships = result.get('relationships', [])
    assert len(relationships) == 2, f"Expected 2 relationships, got {len(relationships)}"

    # Check METADATA_SOURCE relationship
    metadata_rel = next((r for r in relationships if r['type'] == 'METADATA_SOURCE'), None)
    assert metadata_rel is not None, "METADATA_SOURCE relationship not declared"
    assert metadata_rel['from_label'] == 'ImagingDataset'
    assert metadata_rel['to_label'] == 'InstrumentRecord'
    assert 'path' in metadata_rel['from_match']
    assert 'source_file' in metadata_rel['to_match']

    # Check DERIVED_FROM relationship
    derived_rel = next((r for r in relationships if r['type'] == 'DERIVED_FROM'), None)
    assert derived_rel is not None, "DERIVED_FROM relationship not declared"
    assert derived_rel['from_label'] == 'ImagingDataset'
    assert derived_rel['to_label'] == 'File'


def test_bruker_skyscan_wrong_format():
    """Test that interpreter handles non-SkyScan files gracefully."""
    from scidk.interpreters.bruker_skyscan_log import BrukerSkyScanLogInterpreter
    import tempfile

    # Create a non-SkyScan log file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.log', delete=False) as f:
        f.write("Some random log content\nNot a SkyScan file\n")
        temp_path = Path(f.name)

    try:
        interp = BrukerSkyScanLogInterpreter()
        result = interp.interpret(temp_path)

        # Should return gracefully - either error or success with empty nodes
        assert result['status'] in ('error', 'success')
        # If success, should have no or minimal nodes due to missing fields
        if result['status'] == 'success':
            nodes = result.get('nodes', [])
            # Non-SkyScan files won't have the required fields, so nodes may be empty or minimal
            assert isinstance(nodes, list)
    finally:
        temp_path.unlink()


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
