"""SciDK Pipeline — the plugin-agnostic ETL substrate.

Data source plugins (``plugins/<name>/``) implement the
:class:`~scidk.pipeline.plugin_base.DataSourcePlugin` contract: they discover a
source, verify access, and stream raw rows. Everything downstream of that row
stream — column→node mapping, schema targeting, Neo4j writes, FAIR checks,
scheduling, and run history — is owned by this package, not by the plugins.

Built out in Cycle 3B. This module currently exposes only the pieces the plugin
contract itself depends on:

- :mod:`scidk.pipeline.plugin_base` — the ``DataSourcePlugin`` ABC.
- :mod:`scidk.pipeline.transforms` — core (source-agnostic) field transforms.
"""

from .plugin_base import AccessResult, DataSourcePlugin, FindResult
from .transforms import CORE_TRANSFORMS, TransformError

__all__ = [
    "AccessResult",
    "CORE_TRANSFORMS",
    "DataSourcePlugin",
    "FindResult",
    "TransformError",
]
