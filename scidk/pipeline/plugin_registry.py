"""Resolve a source's ``plugin_type`` to a live :class:`DataSourcePlugin`.

A ``pipeline_source`` row stores a plugin type as a string. The runner needs the
object. This is the one place that mapping lives, so a source record does not
have to know how a plugin is imported and the runner does not have to know which
plugins exist.

Resolution order
----------------
1. :data:`BUILTIN_SOURCES` — Pipeline-owned sources, chiefly the local-file
   reader behind file upload. Checked first: it must work even with every plugin
   in ``plugins/`` disabled.
2. :data:`PLUGIN_PACKAGES` — known aliases, so a ``plugin_type`` of
   ``sharepoint`` (the plugin's ``name``), ``sharepoint_intake`` (its package),
   or ``sharepoint_list`` (one of its ``source_types``) all reach the same place.
3. ``plugins.<plugin_type>`` — the general case. Any plugin package exposing a
   module-level ``get_plugin()`` that returns a ``DataSourcePlugin`` resolves
   without being listed here.

Not every ``data_import`` plugin implements the contract yet. ``table_loader``
and ``ilab_table_loader`` register UI templates but have no ``get_plugin()``, and
saying so plainly is the point of :class:`PluginNotAvailable` — the alternative
is a source that appears configurable and fails at run time with an ImportError.
"""
from __future__ import annotations

import importlib
import logging
from typing import Any, Callable, Dict, Optional

from .file_source import TabularFilePlugin
from .plugin_base import DataSourcePlugin

logger = logging.getLogger(__name__)

__all__ = [
    "BUILTIN_SOURCES",
    "PLUGIN_PACKAGES",
    "PluginNotAvailable",
    "is_available",
    "resolve_plugin",
]


class PluginNotAvailable(RuntimeError):
    """No ``DataSourcePlugin`` can be produced for this ``plugin_type``."""


#: Pipeline-owned sources. Values are factories, so nothing is constructed at
#: import time.
BUILTIN_SOURCES: Dict[str, Callable[..., DataSourcePlugin]] = {
    "tabular_file": TabularFilePlugin,
    "file_upload": TabularFilePlugin,
    "csv": TabularFilePlugin,
    "tsv": TabularFilePlugin,
    "excel": TabularFilePlugin,
}

#: ``plugin_type`` → package under ``plugins/``. Aliases exist because the UI
#: has three plausible strings for one plugin and all three should work.
PLUGIN_PACKAGES: Dict[str, str] = {
    "sharepoint": "sharepoint_intake",
    "sharepoint_intake": "sharepoint_intake",
    "sharepoint_list": "sharepoint_intake",
    "sharepoint_library": "sharepoint_intake",
}


def resolve_plugin(plugin_type: str, **kwargs: Any) -> DataSourcePlugin:
    """Return a plugin instance for ``plugin_type``.

    Args:
        plugin_type: The value stored on ``pipeline_source.plugin_type``.
        **kwargs: Passed to the factory. ``base_dir`` for the built-in file
            source; ``provider`` for the SharePoint plugin. Silently dropped when
            the factory does not accept them, so a caller can pass a hint without
            first knowing which plugin it will reach.

    Returns:
        DataSourcePlugin: a fresh instance. Plugins are stateless between calls,
        so callers may keep or discard it freely.

    Raises:
        PluginNotAvailable: Unknown type, or a plugin package that does not
            implement the contract. The message names what was tried.
    """
    key = str(plugin_type or "").strip().lower()
    if not key:
        raise PluginNotAvailable("no plugin_type given")

    builtin = BUILTIN_SOURCES.get(key)
    if builtin is not None:
        return _construct(builtin, kwargs)

    package = PLUGIN_PACKAGES.get(key, key)
    try:
        module = importlib.import_module(f"plugins.{package}")
    except ImportError as e:
        raise PluginNotAvailable(
            f"no data source plugin for {plugin_type!r}: could not import "
            f"plugins.{package} ({e}). Known types: {sorted(known_types())}"
        ) from e

    factory = getattr(module, "get_plugin", None)
    if not callable(factory):
        raise PluginNotAvailable(
            f"plugin {package!r} does not expose get_plugin(), so it does not "
            "implement the DataSourcePlugin contract yet. It can register a UI "
            "template but cannot be run as a Pipeline source."
        )

    plugin = _construct(factory, kwargs)
    if not isinstance(plugin, DataSourcePlugin):
        raise PluginNotAvailable(
            f"plugins.{package}.get_plugin() returned "
            f"{type(plugin).__name__}, which is not a DataSourcePlugin"
        )
    return plugin


def _construct(factory: Callable[..., Any], kwargs: Dict[str, Any]) -> Any:
    """Call ``factory``, passing only the keyword arguments it accepts."""
    import inspect

    if not kwargs:
        return factory()
    try:
        accepted = set(inspect.signature(factory).parameters)
    except (TypeError, ValueError):
        return factory()
    return factory(**{k: v for k, v in kwargs.items() if k in accepted})


def known_types() -> Dict[str, str]:
    """Every ``plugin_type`` this module resolves, mapped to its origin."""
    types = {name: "builtin" for name in BUILTIN_SOURCES}
    types.update({name: f"plugins.{pkg}" for name, pkg in PLUGIN_PACKAGES.items()})
    return types


def is_available(plugin_type: str) -> bool:
    """Whether :func:`resolve_plugin` would succeed, without raising.

    For the UI, which should not offer a Run button for a source whose plugin
    cannot be loaded.
    """
    try:
        resolve_plugin(plugin_type)
        return True
    except Exception:  # noqa: BLE001 - availability is the answer, not an error
        return False


def transform_library_for(plugin: Optional[DataSourcePlugin]) -> Dict[str, Callable]:
    """Return a plugin's transforms, tolerating one that misbehaves.

    A plugin whose ``transform_library()`` raises should not prevent a run whose
    mapping config happens to name no plugin transforms — the mapping engine
    reports an unknown transform name on its own, with a better message.
    """
    if plugin is None:
        return {}
    try:
        library = plugin.transform_library() or {}
    except Exception as e:  # noqa: BLE001
        logger.warning(
            "transform_library() failed for %s: %s", type(plugin).__name__, e
        )
        return {}
    return dict(library)
