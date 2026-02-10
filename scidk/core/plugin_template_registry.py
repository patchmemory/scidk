"""Plugin Template Registry for managing plugin templates.

This registry manages plugin templates (code-based definitions) that can be
instantiated multiple times by users via the UI. Distinct from plugin instances
(user-created configs).

Example:
    Template: "Table Loader" (code-based plugin)
    Instances: "iLab Equipment 2024", "PI Directory", "Lab Resources Q1" (user configs)
"""

import logging
from typing import Dict, List, Optional, Callable

logger = logging.getLogger(__name__)


class PluginTemplateRegistry:
    """Registry for plugin templates that can be instantiated by users."""

    def __init__(self):
        """Initialize the template registry."""
        self.templates: Dict[str, dict] = {}
        logger.info("Plugin template registry initialized")

    def register(self, template_config: dict) -> bool:
        """Register a plugin template.

        Args:
            template_config: Template configuration dict with required fields:
                - id: Unique template identifier (e.g., "table_loader")
                - name: Display name (e.g., "Table Loader")
                - description: Human-readable description
                - category: Category (data_import, api_fetcher, file_importer, etc.)
                - supports_multiple_instances: Boolean, if True users can create multiple instances
                - config_schema: JSON schema for instance configuration
                - handler: Callable that executes the template logic
                Optional fields:
                - icon: Emoji or icon for UI display
                - preset_configs: Predefined configurations for common use cases
                - version: Template version

        Returns:
            bool: True if registration successful, False otherwise
        """
        # Validate required fields
        required_fields = ['id', 'name', 'description', 'category', 'handler']
        for field in required_fields:
            if field not in template_config:
                logger.error(f"Plugin template registration missing required field: {field}")
                return False

        template_id = template_config['id']

        # Check for duplicate registration
        if template_id in self.templates:
            logger.warning(f"Plugin template {template_id} already registered, overwriting")

        # Validate handler is callable
        if not callable(template_config['handler']):
            logger.error(f"Plugin template handler for {template_id} is not callable")
            return False

        # Store template with defaults
        self.templates[template_id] = {
            'id': template_id,
            'name': template_config['name'],
            'description': template_config['description'],
            'category': template_config['category'],
            'supports_multiple_instances': template_config.get('supports_multiple_instances', True),
            'config_schema': template_config.get('config_schema', {}),
            'handler': template_config['handler'],
            'icon': template_config.get('icon', '📦'),
            'preset_configs': template_config.get('preset_configs', {}),
            'version': template_config.get('version', '1.0.0')
        }

        logger.info(f"Registered plugin template: {template_id} ({template_config['name']})")
        return True

    def unregister(self, template_id: str) -> bool:
        """Unregister a plugin template.

        Args:
            template_id: The template ID to unregister

        Returns:
            bool: True if unregistered, False if not found
        """
        if template_id in self.templates:
            template_name = self.templates[template_id]['name']
            del self.templates[template_id]
            logger.info(f"Unregistered plugin template: {template_id} ({template_name})")
            return True
        return False

    def get_template(self, template_id: str) -> Optional[dict]:
        """Get a registered template by ID.

        Args:
            template_id: The template ID

        Returns:
            Template config dict, or None if not found
        """
        return self.templates.get(template_id)

    def list_templates(self, category: Optional[str] = None) -> List[dict]:
        """List all registered templates, optionally filtered by category.

        Args:
            category: Optional category filter

        Returns:
            List of template config dicts (without handler for serialization)
        """
        templates = list(self.templates.values())

        if category:
            templates = [t for t in templates if t['category'] == category]

        # Return without handler (not JSON serializable)
        return [
            {k: v for k, v in t.items() if k != 'handler'}
            for t in templates
        ]

    def execute_template(self, template_id: str, instance_config: dict) -> dict:
        """Execute a template handler with an instance configuration.

        Args:
            template_id: The template ID
            instance_config: The instance configuration to pass to the handler

        Returns:
            dict: Execution result from the handler

        Raises:
            ValueError: If template not found
        """
        template = self.get_template(template_id)
        if not template:
            raise ValueError(f"Template '{template_id}' not found")

        handler = template['handler']
        try:
            result = handler(instance_config)
            logger.info(f"Executed template {template_id} successfully")
            return result
        except Exception as e:
            logger.error(f"Error executing template {template_id}: {e}")
            raise

    def clear(self):
        """Clear all registered templates (useful for testing)."""
        self.templates.clear()
        logger.info("Cleared all plugin templates")
