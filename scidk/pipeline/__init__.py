"""SciDK Pipeline — the plugin-agnostic ETL substrate.

Data source plugins (``plugins/<name>/``) implement the
:class:`~scidk.pipeline.plugin_base.DataSourcePlugin` contract: they discover a
source, verify access, and stream raw rows. Everything downstream of that row
stream — column→node mapping, schema targeting, Neo4j writes, FAIR checks,
scheduling, and run history — is owned by this package, not by the plugins.

The pieces, roughly in the order a run touches them:

``plugin_base``      The ``DataSourcePlugin`` ABC every plugin implements.
``plugin_registry``  ``plugin_type`` string → a live plugin instance.
``file_source``      Built-in local CSV/TSV/Excel source, behind file upload.
``transforms``       Core (source-agnostic) field transforms.
``identifiers``      Cypher identifier guards for everything written.
``mapping_engine``   Row stream + mapping config → node/relationship declarations.
``mapping_schema``   JSON Schema the mapping config format must satisfy.
``runner``           One source: find → access → validate → fetch → map → write.
``fair_check``       What a run would write, sampled and previewed, writing nothing.
``orchestrator``     One source, or a whole DAG of them in dependency order.
``store``            ``pipeline_source`` and ``pipeline`` persistence.
``run_history``      ``pipeline_run`` persistence.
``scheduler``        Cron schedules, in a jobstore the gunicorn master shares.

Imports here are kept to the light modules. ``runner``, ``fair_check``,
``orchestrator``, ``store`` and ``scheduler`` pull in Neo4j, SQLite and
APScheduler, so importing this package does not drag those in — import them
directly instead.
"""

from .identifiers import IdentifierError, check_identifier, require_identifier
from .mapping_engine import (
    MappingConfigError,
    MappingEngine,
    ValidationReport,
    validate_against_schema,
)
from .plugin_base import AccessResult, DataSourcePlugin, FindResult
from .transforms import CORE_TRANSFORMS, TransformError

__all__ = [
    "AccessResult",
    "CORE_TRANSFORMS",
    "DataSourcePlugin",
    "FindResult",
    "IdentifierError",
    "MappingConfigError",
    "MappingEngine",
    "TransformError",
    "ValidationReport",
    "check_identifier",
    "require_identifier",
    "validate_against_schema",
]
