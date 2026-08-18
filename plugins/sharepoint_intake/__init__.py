"""SharePoint Intake Plugin for SciDK.

A ``DataSourcePlugin`` over SharePoint lists and document libraries. It discovers
a list (``find()``), verifies credentials (``access()``), streams rows as raw
dicts (``fetch()``), and publishes SharePoint-specific field transforms
(``transform_library()``).

It does not ingest. Column→node mapping, Neo4j writes, FAIR reporting,
scheduling, and run history belong to :mod:`scidk.pipeline`, which consumes the
row stream. ``configs/aipt_intake_mapping.json`` is the reference mapping for the
AIPT deployment.
"""

import logging

from . import config
from .plugin import SharePointPlugin

logger = logging.getLogger(__name__)

__all__ = ["SharePointPlugin", "get_plugin", "handle_sharepoint_discovery", "register_plugin"]


def get_plugin(provider=None) -> SharePointPlugin:
    """Return a plugin instance for the Pipeline to call.

    Args:
        provider: Optional rclone provider override (see :class:`SharePointPlugin`).

    Returns:
        SharePointPlugin: stateless, so callers may keep or discard it freely.
    """
    return SharePointPlugin(provider=provider)


def handle_sharepoint_discovery(instance_config: dict) -> dict:
    """Template handler: discover what a configured list contains.

    Discovery is the only action the plugin can perform on its own — running a
    pipeline is initiated through :mod:`scidk.pipeline`, which owns the mapping
    and the writes.

    Args:
        instance_config: Instance configuration. Keys: ``source_path`` (rclone or
            local path to the export), ``sheet``, ``sample_rows``, ``timeout_sec``.

    Returns:
        dict: a ``FindResult`` — ``{ok, columns, row_count, sample, metadata, error}``.
    """
    return get_plugin().find(instance_config or {})


def register_plugin(app):
    """Register the SharePoint Intake data source template with SciDK.

    Args:
        app: Flask application instance.

    Returns:
        dict: Plugin metadata.
    """
    registry = app.extensions['scidk']['plugin_templates']

    success = registry.register({
        'id': 'sharepoint_intake',
        'name': 'SharePoint Intake',
        'description': 'Connect a SharePoint list or document library as a data source. '
                       'Mapping to the graph is configured in the Pipeline.',
        'category': 'data_import',
        'icon': '📥',
        'supports_multiple_instances': True,
        'version': '2.0.0',
        'plugin_name': SharePointPlugin.name,
        'source_types': list(SharePointPlugin.source_types),
        'reference_mapping': config.REFERENCE_MAPPING,
        'graph_behavior': {
            # The Pipeline creates labels from the mapping config; the plugin
            # only supplies rows and therefore names no labels of its own.
            'can_create_label': False,
            'label_source': 'pipeline',
            'sync_strategy': 'pipeline',
            'supports_preview': True,
        },
        'config_schema': {
            'type': 'object',
            'properties': {
                'instance_name': {
                    'type': 'string',
                    'description': 'Friendly name for this data source',
                    'required': True,
                },
                'source_path': {
                    'type': 'string',
                    'description': 'rclone remote path (remote:Site/Lists/Name.csv) or local path '
                                   'of the exported SharePoint list. Falls back to the configured '
                                   f'"{config.SETTING_SYNC_REMOTE}" setting when omitted.',
                },
                'sheet': {
                    'type': 'string',
                    'description': 'Worksheet name, for an Excel export. Defaults to the first sheet.',
                },
                'sample_rows': {
                    'type': 'number',
                    'default': 3,
                    'description': 'Rows returned as a preview sample by discovery',
                },
                'max_scan_rows': {
                    'type': 'number',
                    'default': 100000,
                    'description': 'Rows discovery counts before reporting an unknown row '
                                   'count. Lower it for a list too large to count quickly.',
                },
                'timeout_sec': {
                    'type': 'number',
                    'default': 120,
                    'description': 'Timeout (seconds) for a buffered remote read',
                },
            },
        },
        'handler': handle_sharepoint_discovery,
        'preset_configs': {
            'sharepoint_list': {
                'name': 'SharePoint list',
                'description': 'A SharePoint list exported to CSV and reachable via rclone',
                'config': {},
            },
            'sharepoint_library': {
                'name': 'SharePoint document library',
                'description': 'A document library export (CSV or Excel) reachable via rclone',
                'config': {},
            },
        },
    })

    if success:
        logger.info("SharePoint Intake plugin template registered successfully")
    else:
        logger.error("Failed to register SharePoint Intake plugin template")

    return {
        'name': 'SharePoint Intake',
        'version': '2.0.0',
        'author': 'SciDK Team',
        'description': 'SharePoint lists as a SciDK data source: discover, verify access, and '
                       'stream rows for the Pipeline to map into the knowledge graph.',
    }
