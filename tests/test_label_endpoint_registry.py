"""Tests for Label Endpoint Registry.

Tests the plugin label endpoint registration system that allows plugins to
register API endpoints that map to Label types.
"""

import pytest
from scidk.core.label_endpoint_registry import LabelEndpointRegistry


@pytest.fixture
def registry():
    """Create a fresh registry for each test."""
    return LabelEndpointRegistry()


def test_registry_initialization(registry):
    """Test registry initializes empty."""
    assert len(registry.list_endpoints()) == 0


def test_register_endpoint(registry):
    """Test registering a basic endpoint."""
    config = {
        'name': 'iLab Services',
        'endpoint': '/api/integrations/ilab',
        'label_type': 'iLabService'
    }

    result = registry.register(config)
    assert result is True

    endpoints = registry.list_endpoints()
    assert len(endpoints) == 1
    assert endpoints[0]['name'] == 'iLab Services'
    assert endpoints[0]['endpoint'] == '/api/integrations/ilab'
    assert endpoints[0]['label_type'] == 'iLabService'
    assert endpoints[0]['source'] == 'plugin'


def test_register_endpoint_with_all_fields(registry):
    """Test registering an endpoint with all optional fields."""
    config = {
        'name': 'iLab Services',
        'endpoint': '/api/integrations/ilab',
        'label_type': 'iLabService',
        'auth_required': True,
        'test_url': '/api/integrations/ilab/test',
        'plugin': 'ilab_plugin',
        'description': 'Integration with iLab service management system',
        'config_schema': {'type': 'object'}
    }

    result = registry.register(config)
    assert result is True

    endpoint = registry.get_endpoint('/api/integrations/ilab')
    assert endpoint['auth_required'] is True
    assert endpoint['test_url'] == '/api/integrations/ilab/test'
    assert endpoint['plugin'] == 'ilab_plugin'
    assert endpoint['description'] == 'Integration with iLab service management system'
    assert endpoint['config_schema'] == {'type': 'object'}


def test_register_endpoint_missing_required_field(registry):
    """Test that registration fails if required field is missing."""
    config = {
        'name': 'iLab Services',
        'endpoint': '/api/integrations/ilab'
        # Missing 'label_type'
    }

    result = registry.register(config)
    assert result is False
    assert len(registry.list_endpoints()) == 0


def test_register_duplicate_endpoint_overwrites(registry):
    """Test that registering duplicate endpoint path overwrites."""
    config1 = {
        'name': 'iLab Services V1',
        'endpoint': '/api/integrations/ilab',
        'label_type': 'iLabService'
    }

    config2 = {
        'name': 'iLab Services V2',
        'endpoint': '/api/integrations/ilab',
        'label_type': 'iLabServiceV2'
    }

    registry.register(config1)
    registry.register(config2)

    endpoints = registry.list_endpoints()
    assert len(endpoints) == 1
    assert endpoints[0]['name'] == 'iLab Services V2'
    assert endpoints[0]['label_type'] == 'iLabServiceV2'


def test_get_endpoint(registry):
    """Test retrieving a specific endpoint."""
    config = {
        'name': 'iLab Services',
        'endpoint': '/api/integrations/ilab',
        'label_type': 'iLabService'
    }

    registry.register(config)

    endpoint = registry.get_endpoint('/api/integrations/ilab')
    assert endpoint is not None
    assert endpoint['name'] == 'iLab Services'

    missing = registry.get_endpoint('/api/integrations/missing')
    assert missing is None


def test_unregister_endpoint(registry):
    """Test unregistering an endpoint."""
    config = {
        'name': 'iLab Services',
        'endpoint': '/api/integrations/ilab',
        'label_type': 'iLabService'
    }

    registry.register(config)
    assert len(registry.list_endpoints()) == 1

    result = registry.unregister('/api/integrations/ilab')
    assert result is True
    assert len(registry.list_endpoints()) == 0

    # Unregistering again should return False
    result = registry.unregister('/api/integrations/ilab')
    assert result is False


def test_list_by_plugin(registry):
    """Test filtering endpoints by plugin."""
    configs = [
        {
            'name': 'iLab Services',
            'endpoint': '/api/integrations/ilab',
            'label_type': 'iLabService',
            'plugin': 'ilab_plugin'
        },
        {
            'name': 'Slack Integration',
            'endpoint': '/api/integrations/slack',
            'label_type': 'SlackMessage',
            'plugin': 'slack_plugin'
        },
        {
            'name': 'iLab Equipment',
            'endpoint': '/api/integrations/ilab/equipment',
            'label_type': 'Equipment',
            'plugin': 'ilab_plugin'
        }
    ]

    for config in configs:
        registry.register(config)

    ilab_endpoints = registry.list_by_plugin('ilab_plugin')
    assert len(ilab_endpoints) == 2
    assert all(e['plugin'] == 'ilab_plugin' for e in ilab_endpoints)

    slack_endpoints = registry.list_by_plugin('slack_plugin')
    assert len(slack_endpoints) == 1
    assert slack_endpoints[0]['name'] == 'Slack Integration'


def test_list_by_label_type(registry):
    """Test filtering endpoints by label type."""
    configs = [
        {
            'name': 'iLab Services',
            'endpoint': '/api/integrations/ilab/services',
            'label_type': 'iLabService',
            'plugin': 'ilab_plugin'
        },
        {
            'name': 'iLab Services Alt',
            'endpoint': '/api/integrations/ilab/services/alt',
            'label_type': 'iLabService',
            'plugin': 'ilab_alt_plugin'
        },
        {
            'name': 'Equipment',
            'endpoint': '/api/integrations/equipment',
            'label_type': 'Equipment',
            'plugin': 'equipment_plugin'
        }
    ]

    for config in configs:
        registry.register(config)

    service_endpoints = registry.list_by_label_type('iLabService')
    assert len(service_endpoints) == 2
    assert all(e['label_type'] == 'iLabService' for e in service_endpoints)

    equipment_endpoints = registry.list_by_label_type('Equipment')
    assert len(equipment_endpoints) == 1


def test_clear_registry(registry):
    """Test clearing all endpoints."""
    configs = [
        {
            'name': 'Endpoint 1',
            'endpoint': '/api/integrations/test1',
            'label_type': 'Type1'
        },
        {
            'name': 'Endpoint 2',
            'endpoint': '/api/integrations/test2',
            'label_type': 'Type2'
        }
    ]

    for config in configs:
        registry.register(config)

    assert len(registry.list_endpoints()) == 2

    registry.clear()
    assert len(registry.list_endpoints()) == 0


def test_endpoint_defaults(registry):
    """Test that optional fields have correct defaults."""
    config = {
        'name': 'Test Endpoint',
        'endpoint': '/api/test',
        'label_type': 'TestType'
    }

    registry.register(config)
    endpoint = registry.get_endpoint('/api/test')

    assert endpoint['auth_required'] is False
    assert endpoint['test_url'] is None
    assert endpoint['plugin'] == 'unknown'
    assert endpoint['description'] == ''
    assert endpoint['config_schema'] == {}
    assert endpoint['source'] == 'plugin'


def test_multiple_plugins_registration(registry):
    """Test multiple plugins can register different endpoints."""
    plugin1_config = {
        'name': 'Plugin 1 Endpoint',
        'endpoint': '/api/integrations/plugin1',
        'label_type': 'Plugin1Type',
        'plugin': 'plugin1'
    }

    plugin2_config = {
        'name': 'Plugin 2 Endpoint',
        'endpoint': '/api/integrations/plugin2',
        'label_type': 'Plugin2Type',
        'plugin': 'plugin2'
    }

    registry.register(plugin1_config)
    registry.register(plugin2_config)

    all_endpoints = registry.list_endpoints()
    assert len(all_endpoints) == 2

    plugin1_endpoints = registry.list_by_plugin('plugin1')
    assert len(plugin1_endpoints) == 1
    assert plugin1_endpoints[0]['name'] == 'Plugin 1 Endpoint'

    plugin2_endpoints = registry.list_by_plugin('plugin2')
    assert len(plugin2_endpoints) == 1
    assert plugin2_endpoints[0]['name'] == 'Plugin 2 Endpoint'
