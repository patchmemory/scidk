"""
tests/test_schema.py

Tests for the SciDK schema layer:
  - Sanitization pipeline
  - Label registry loading
  - SciDKNode base class
  - Stub generation
  - Fixture validation for built-in labels
"""

import os
import sys
import pytest

# Ensure scidk package is importable from repo root
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from scidk.schema.base import SciDKNode
from scidk.schema.sanitization import apply_sanitization
from scidk.schema.registry import LabelRegistry, LabelDefinition, PropertyDefinition


# ─── Sanitization pipeline tests ──────────────────────────────────────────────

class TestSanitization:

    def test_none_rule_passes_through(self):
        rules = {'name': {'rule': 'none'}}
        result = apply_sanitization({'name': 'Test Value'}, rules)
        assert result['name'] == 'Test Value'

    def test_redact_removes_property(self):
        rules = {'donor_name': {'rule': 'redact'}}
        result = apply_sanitization({'donor_name': 'John Doe', 'sample_id': 'S001'}, rules)
        assert 'donor_name' not in result
        assert result['sample_id'] == 'S001'

    def test_hash_is_deterministic(self):
        rules = {'institution': {'rule': 'hash'}}
        result1 = apply_sanitization({'institution': 'University of Example'}, rules)
        result2 = apply_sanitization({'institution': 'University of Example'}, rules)
        assert result1['institution'] == result2['institution']
        assert result1['institution'].startswith('hash:')

    def test_hash_different_inputs_different_outputs(self):
        rules = {'institution': {'rule': 'hash'}}
        r1 = apply_sanitization({'institution': 'University A'}, rules)
        r2 = apply_sanitization({'institution': 'University B'}, rules)
        assert r1['institution'] != r2['institution']

    def test_bin_integer(self):
        rules = {'donor_age': {'rule': 'bin', 'bin_size': 10, 'units': 'years'}}
        result = apply_sanitization({'donor_age': 45}, rules)
        assert result['donor_age'] == '40-50 years'

    def test_bin_boundary(self):
        rules = {'donor_age': {'rule': 'bin', 'bin_size': 10, 'units': 'years'}}
        result = apply_sanitization({'donor_age': 40}, rules)
        assert result['donor_age'] == '40-50 years'

    def test_bin_zero(self):
        rules = {'score': {'rule': 'bin', 'bin_size': 5}}
        result = apply_sanitization({'score': 3}, rules)
        assert result['score'] == '0-5'

    def test_truncate_to_integer(self):
        rules = {'weight': {'rule': 'truncate', 'decimal_places': 0}}
        result = apply_sanitization({'weight': 72.8}, rules)
        assert result['weight'] == 73

    def test_truncate_to_one_decimal(self):
        rules = {'score': {'rule': 'truncate', 'decimal_places': 1}}
        result = apply_sanitization({'score': 3.14159}, rules)
        assert result['score'] == 3.1

    def test_unknown_property_passes_through(self):
        rules = {'known_prop': {'rule': 'redact'}}
        result = apply_sanitization({'known_prop': 'x', 'unknown_prop': 'y'}, rules)
        assert 'known_prop' not in result
        assert result['unknown_prop'] == 'y'

    def test_empty_rules_passes_all_through(self):
        props = {'a': 1, 'b': 'two', 'c': 3.0}
        result = apply_sanitization(props, {})
        assert result == props

    def test_failed_rule_passes_through_with_warning(self, caplog):
        """A rule that fails should not crash the write — pass through with warning."""
        import logging
        rules = {'age': {'rule': 'bin'}}  # missing bin_size config
        with caplog.at_level(logging.WARNING):
            result = apply_sanitization({'age': 45}, rules)
        assert result['age'] == 45  # passed through unchanged
        assert 'bin_size' in caplog.text or 'failed' in caplog.text.lower()


# ─── Label registry tests ──────────────────────────────────────────────────────

class TestLabelRegistry:

    @pytest.fixture(autouse=True)
    def load_builtin_labels(self):
        """Load built-in labels before each test."""
        builtin_dir = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            'scidk', 'labels', 'builtin'
        )
        if os.path.isdir(builtin_dir):
            LabelRegistry.load([builtin_dir])

    def test_sample_label_loads(self):
        label = LabelRegistry.get('Sample')
        assert label is not None
        assert label.neo4j_label == 'Sample'

    def test_imaging_dataset_label_loads(self):
        label = LabelRegistry.get('ImagingDataset')
        assert label is not None

    def test_instrument_record_label_loads(self):
        label = LabelRegistry.get('InstrumentRecord')
        assert label is not None

    def test_sample_key_property(self):
        label = LabelRegistry.get('Sample')
        assert label.key_property == 'sample_id'

    def test_sample_sanitization_rules(self):
        label = LabelRegistry.get('Sample')
        rules = label.sanitization_rules
        assert rules['donor_name']['rule'] == 'redact'
        assert rules['donor_age']['rule'] == 'bin'
        assert rules['institution']['rule'] == 'hash'
        assert 'sample_id' not in rules  # none rule not included

    def test_sample_required_properties(self):
        label = LabelRegistry.get('Sample')
        assert 'sample_id' in label.required_properties

    def test_unknown_label_returns_none(self):
        label = LabelRegistry.get('NonExistentLabel')
        assert label is None

    def test_all_returns_dict(self):
        all_labels = LabelRegistry.all()
        assert isinstance(all_labels, dict)
        assert len(all_labels) > 0

    def test_cypher_constraints_generated(self):
        label = LabelRegistry.get('Sample')
        constraints = label.generate_cypher_constraints()
        assert any('UNIQUE' in c for c in constraints)
        assert any('sample_id' in c for c in constraints)


# ─── Sample label fixture validation ──────────────────────────────────────────

class TestSampleLabelFixture:
    """Validate that the Sample label fixture matches sanitization behavior."""

    @pytest.fixture(autouse=True)
    def load_labels(self):
        builtin_dir = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            'scidk', 'labels', 'builtin'
        )
        if os.path.isdir(builtin_dir):
            LabelRegistry.load([builtin_dir])

    def test_fixture_sanitization_matches_expected(self):
        label = LabelRegistry.get('Sample')
        fixture = label.test_fixture

        valid_node = fixture['valid_node']
        expected = fixture['expected_stored']

        result = apply_sanitization(valid_node, label.sanitization_rules)

        # Check expected properties are present with correct values
        for key, expected_val in expected.items():
            if not key.startswith('#'):
                assert key in result, f"Expected property '{key}' missing from sanitized result"
                assert result[key] == expected_val, (
                    f"Property '{key}': expected {expected_val!r}, got {result[key]!r}"
                )

        # Check redacted properties are absent
        assert 'donor_name' not in result, "donor_name should be redacted"


# ─── SciDKNode base class tests ───────────────────────────────────────────────

class TestSciDKNode:

    def test_basic_instantiation(self):
        class TestNode(SciDKNode):
            _label = "TestNode"
            _key_property = "node_id"
            _sanitization = {}
            _required = ["node_id"]
            node_id: str = None
            name: str = None

        node = TestNode(node_id="T001", name="Test")
        assert node.node_id == "T001"
        assert node.name == "Test"

    def test_unknown_properties_stored_with_prefix(self):
        class TestNode(SciDKNode):
            _label = "TestNode"
            _key_property = "node_id"
            _sanitization = {}
            _required = []
            node_id: str = None

        node = TestNode(node_id="T001", unknown_field="value")
        assert hasattr(node, 'raw_unknown_field')
        assert node.raw_unknown_field == "value"

    def test_validation_catches_missing_required(self):
        class TestNode(SciDKNode):
            _label = "TestNode"
            _key_property = "node_id"
            _sanitization = {}
            _required = ["node_id"]
            node_id: str = None

        node = TestNode()  # node_id not set
        errors = node.validate()
        assert len(errors) > 0
        assert "node_id" in errors[0]

    def test_to_cypher_props_applies_sanitization(self):
        class TestNode(SciDKNode):
            _label = "TestNode"
            _key_property = "node_id"
            _sanitization = {
                'secret': {'rule': 'redact'},
                'age': {'rule': 'bin', 'bin_size': 10},
            }
            _required = []
            node_id: str = None
            secret: str = None
            age: int = None

        node = TestNode(node_id="T001", secret="hidden", age=45)
        props = node.to_cypher_props()
        assert 'secret' not in props
        assert props['age'] == '40-50'
        assert props['node_id'] == 'T001'

    def test_merge_cypher_returns_valid_structure(self):
        class TestNode(SciDKNode):
            _label = "Sample"
            _key_property = "sample_id"
            _sanitization = {}
            _required = []
            sample_id: str = None
            species: str = None

        node = TestNode(sample_id="S001", species="Homo sapiens")
        cypher, params = node.merge_cypher()
        assert "MERGE" in cypher
        assert "Sample" in cypher
        assert "sample_id" in cypher
        assert params['key_val'] == "S001"
        assert params['props']['species'] == "Homo sapiens"

    def test_merge_cypher_raises_if_key_is_none(self):
        class TestNode(SciDKNode):
            _label = "Sample"
            _key_property = "sample_id"
            _sanitization = {}
            _required = []
            sample_id: str = None

        node = TestNode()  # sample_id is None
        with pytest.raises(ValueError, match="key_property"):
            node.merge_cypher()

    def test_repr(self):
        class TestNode(SciDKNode):
            _label = "Sample"
            _key_property = "sample_id"
            _sanitization = {}
            _required = []
            sample_id: str = None

        node = TestNode(sample_id="S001")
        assert "Sample" in repr(node)
        assert "S001" in repr(node)
