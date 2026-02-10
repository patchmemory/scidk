"""Tests for Plugin Template Registry."""

import pytest
from scidk.core.plugin_template_registry import PluginTemplateRegistry


def dummy_handler(config):
    """Dummy handler for testing."""
    return {'status': 'success', 'config': config}


class TestPluginTemplateRegistryCategories:
    """Test category validation in plugin template registry."""

    def test_valid_data_import_category(self):
        """Test that data_import category is accepted with graph_behavior."""
        registry = PluginTemplateRegistry()

        result = registry.register({
            'id': 'test_importer',
            'name': 'Test Importer',
            'description': 'Test data import plugin',
            'category': 'data_import',
            'handler': dummy_handler,
            'graph_behavior': {
                'can_create_label': True,
                'label_source': 'table_columns'
            }
        })

        assert result is True
        template = registry.get_template('test_importer')
        assert template is not None
        assert template['category'] == 'data_import'
        assert template['graph_behavior']['can_create_label'] is True

    def test_valid_graph_inject_category(self):
        """Test that graph_inject category is accepted."""
        registry = PluginTemplateRegistry()

        result = registry.register({
            'id': 'test_injector',
            'name': 'Test Graph Injector',
            'description': 'Test graph inject plugin',
            'category': 'graph_inject',
            'handler': dummy_handler
        })

        assert result is True
        template = registry.get_template('test_injector')
        assert template['category'] == 'graph_inject'

    def test_valid_enrichment_category(self):
        """Test that enrichment category is accepted."""
        registry = PluginTemplateRegistry()

        result = registry.register({
            'id': 'test_enricher',
            'name': 'Test Enricher',
            'description': 'Test enrichment plugin',
            'category': 'enrichment',
            'handler': dummy_handler
        })

        assert result is True
        template = registry.get_template('test_enricher')
        assert template['category'] == 'enrichment'

    def test_valid_exporter_category(self):
        """Test that exporter category is accepted."""
        registry = PluginTemplateRegistry()

        result = registry.register({
            'id': 'test_exporter',
            'name': 'Test Exporter',
            'description': 'Test exporter plugin',
            'category': 'exporter',
            'handler': dummy_handler
        })

        assert result is True
        template = registry.get_template('test_exporter')
        assert template['category'] == 'exporter'

    def test_invalid_category(self):
        """Test that invalid categories are rejected."""
        registry = PluginTemplateRegistry()

        result = registry.register({
            'id': 'bad_plugin',
            'name': 'Bad Plugin',
            'description': 'Plugin with invalid category',
            'category': 'invalid_category',
            'handler': dummy_handler
        })

        assert result is False
        template = registry.get_template('bad_plugin')
        assert template is None

    def test_missing_category_defaults_to_exporter(self):
        """Test that missing category defaults to 'exporter'."""
        registry = PluginTemplateRegistry()

        result = registry.register({
            'id': 'no_category',
            'name': 'No Category Plugin',
            'description': 'Plugin without category',
            'handler': dummy_handler
        })

        assert result is True
        template = registry.get_template('no_category')
        assert template is not None
        assert template['category'] == 'exporter'

    def test_data_import_without_graph_behavior_logs_warning(self):
        """Test that data_import without graph_behavior succeeds but logs warning."""
        registry = PluginTemplateRegistry()

        # Should succeed (warning only)
        result = registry.register({
            'id': 'importer_no_behavior',
            'name': 'Importer Without Behavior',
            'description': 'Data import plugin without graph_behavior',
            'category': 'data_import',
            'handler': dummy_handler
        })

        assert result is True
        template = registry.get_template('importer_no_behavior')
        assert template is not None
        assert template['category'] == 'data_import'
        # graph_behavior should be empty dict
        assert template['graph_behavior'] == {}

    def test_data_import_with_partial_graph_behavior(self):
        """Test that data_import with partial graph_behavior logs warning."""
        registry = PluginTemplateRegistry()

        result = registry.register({
            'id': 'importer_partial',
            'name': 'Importer Partial Behavior',
            'description': 'Data import plugin with incomplete graph_behavior',
            'category': 'data_import',
            'handler': dummy_handler,
            'graph_behavior': {
                'can_create_label': True
                # Missing 'label_source'
            }
        })

        assert result is True
        template = registry.get_template('importer_partial')
        assert template['category'] == 'data_import'
        assert template['graph_behavior']['can_create_label'] is True

    def test_graph_behavior_stored_for_all_categories(self):
        """Test that graph_behavior is stored even for non-data_import categories."""
        registry = PluginTemplateRegistry()

        result = registry.register({
            'id': 'exporter_with_behavior',
            'name': 'Exporter With Behavior',
            'description': 'Exporter with graph_behavior',
            'category': 'exporter',
            'handler': dummy_handler,
            'graph_behavior': {
                'custom_key': 'custom_value'
            }
        })

        assert result is True
        template = registry.get_template('exporter_with_behavior')
        assert template['graph_behavior']['custom_key'] == 'custom_value'

    def test_list_templates_includes_category(self):
        """Test that list_templates includes category field."""
        registry = PluginTemplateRegistry()

        registry.register({
            'id': 'plugin1',
            'name': 'Plugin 1',
            'description': 'Test plugin 1',
            'category': 'data_import',
            'handler': dummy_handler
        })

        registry.register({
            'id': 'plugin2',
            'name': 'Plugin 2',
            'description': 'Test plugin 2',
            'category': 'exporter',
            'handler': dummy_handler
        })

        templates = registry.list_templates()
        assert len(templates) == 2

        # Check categories are included
        categories = {t['category'] for t in templates}
        assert 'data_import' in categories
        assert 'exporter' in categories

    def test_list_templates_filter_by_category(self):
        """Test filtering templates by category."""
        registry = PluginTemplateRegistry()

        registry.register({
            'id': 'importer1',
            'name': 'Importer 1',
            'description': 'Test importer 1',
            'category': 'data_import',
            'handler': dummy_handler
        })

        registry.register({
            'id': 'importer2',
            'name': 'Importer 2',
            'description': 'Test importer 2',
            'category': 'data_import',
            'handler': dummy_handler
        })

        registry.register({
            'id': 'exporter1',
            'name': 'Exporter 1',
            'description': 'Test exporter 1',
            'category': 'exporter',
            'handler': dummy_handler
        })

        # Filter by data_import
        importers = registry.list_templates(category='data_import')
        assert len(importers) == 2
        assert all(t['category'] == 'data_import' for t in importers)

        # Filter by exporter
        exporters = registry.list_templates(category='exporter')
        assert len(exporters) == 1
        assert exporters[0]['category'] == 'exporter'

    def test_all_valid_categories(self):
        """Test that all VALID_CATEGORIES are accepted."""
        registry = PluginTemplateRegistry()

        for category in PluginTemplateRegistry.VALID_CATEGORIES:
            result = registry.register({
                'id': f'test_{category}',
                'name': f'Test {category}',
                'description': f'Test {category} plugin',
                'category': category,
                'handler': dummy_handler
            })
            assert result is True, f"Category '{category}' should be valid"

            template = registry.get_template(f'test_{category}')
            assert template['category'] == category
