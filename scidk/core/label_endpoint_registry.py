"""Label Endpoint Registry for plugin-registered API endpoints.

This registry allows plugins to register API endpoints that map to Label types.
Registered endpoints appear in the Integrations settings page and can be:
- Configured (auth, URL parameters)
- Tested (test connection button)
- Used in integration workflows

Example plugin registration:
    def register_plugin(app):
        registry = app.extensions['scidk']['label_endpoints']
        registry.register({
            'name': 'iLab Services',
            'endpoint': '/api/integrations/ilab',
            'label_type': 'iLabService',
            'auth_required': True,
            'test_url': '/api/integrations/ilab/test',
            'plugin': 'ilab_plugin',
            'description': 'Integration with iLab service management system'
        })
"""

import logging
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class LabelEndpointRegistry:
    """Registry for plugin-registered label endpoints."""

    def __init__(self):
        """Initialize the registry."""
        self.endpoints: Dict[str, dict] = {}
        logger.info("Label endpoint registry initialized")

    def register(self, endpoint_config: dict) -> bool:
        """Register a label endpoint from a plugin.

        Args:
            endpoint_config: Endpoint configuration dict with required fields:
                - name: Display name (e.g., "iLab Services")
                - endpoint: API endpoint path (e.g., "/api/integrations/ilab")
                - label_type: Target label type in schema (e.g., "iLabService")
                Optional fields:
                - auth_required: Whether authentication is required (default: False)
                - test_url: URL for testing connection (default: None)
                - plugin: Plugin name that registered this endpoint
                - description: Human-readable description
                - config_schema: JSON schema for configuration options

        Returns:
            bool: True if registration successful, False otherwise
        """
        # Validate required fields
        required_fields = ['name', 'endpoint', 'label_type']
        for field in required_fields:
            if field not in endpoint_config:
                logger.error(f"Label endpoint registration missing required field: {field}")
                return False

        endpoint_path = endpoint_config['endpoint']

        # Check for duplicate registration
        if endpoint_path in self.endpoints:
            logger.warning(f"Label endpoint {endpoint_path} already registered, overwriting")

        # Store endpoint config with defaults
        self.endpoints[endpoint_path] = {
            'name': endpoint_config['name'],
            'endpoint': endpoint_path,
            'label_type': endpoint_config['label_type'],
            'auth_required': endpoint_config.get('auth_required', False),
            'test_url': endpoint_config.get('test_url'),
            'plugin': endpoint_config.get('plugin', 'unknown'),
            'description': endpoint_config.get('description', ''),
            'config_schema': endpoint_config.get('config_schema', {}),
            'source': 'plugin'  # Mark as plugin-registered vs manually configured
        }

        logger.info(f"Registered label endpoint: {endpoint_path} ({endpoint_config['name']}) "
                   f"-> {endpoint_config['label_type']}")
        return True

    def unregister(self, endpoint_path: str) -> bool:
        """Unregister a label endpoint.

        Args:
            endpoint_path: The endpoint path to unregister

        Returns:
            bool: True if unregistered, False if not found
        """
        if endpoint_path in self.endpoints:
            endpoint_name = self.endpoints[endpoint_path]['name']
            del self.endpoints[endpoint_path]
            logger.info(f"Unregistered label endpoint: {endpoint_path} ({endpoint_name})")
            return True
        return False

    def get_endpoint(self, endpoint_path: str) -> Optional[dict]:
        """Get a registered endpoint by path.

        Args:
            endpoint_path: The endpoint path

        Returns:
            Endpoint config dict, or None if not found
        """
        return self.endpoints.get(endpoint_path)

    def list_endpoints(self) -> List[dict]:
        """List all registered label endpoints.

        Returns:
            List of endpoint config dicts
        """
        return list(self.endpoints.values())

    def list_by_plugin(self, plugin_name: str) -> List[dict]:
        """List endpoints registered by a specific plugin.

        Args:
            plugin_name: Name of the plugin

        Returns:
            List of endpoint config dicts
        """
        return [
            endpoint for endpoint in self.endpoints.values()
            if endpoint.get('plugin') == plugin_name
        ]

    def list_by_label_type(self, label_type: str) -> List[dict]:
        """List endpoints that map to a specific label type.

        Args:
            label_type: Label type name

        Returns:
            List of endpoint config dicts
        """
        return [
            endpoint for endpoint in self.endpoints.values()
            if endpoint['label_type'] == label_type
        ]

    def clear(self):
        """Clear all registered endpoints (useful for testing)."""
        self.endpoints.clear()
        logger.info("Cleared all label endpoints")
