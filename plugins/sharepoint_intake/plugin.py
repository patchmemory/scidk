"""``SharePointPlugin`` — the ``DataSourcePlugin`` contract for SharePoint lists.

This module is the whole plugin surface. It discovers a list, verifies access,
streams rows, and publishes SharePoint-specific transforms — and does nothing
else. Column→node mapping, Neo4j writes, FAIR reporting, scheduling, and run
history belong to :mod:`scidk.pipeline` (built in Cycle 3B); the reference
mapping for the AIPT deployment is ``configs/aipt_intake_mapping.json``.

See :class:`scidk.pipeline.plugin_base.DataSourcePlugin` for the FAIR rationale
behind the four methods.
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Dict, Iterator, Optional

from scidk.pipeline.plugin_base import AccessResult, DataSourcePlugin, FindResult

from . import config as cfg
from . import ingest
from .transforms import SHAREPOINT_TRANSFORMS

logger = logging.getLogger(__name__)

#: Instance-config keys checked, in order, for the source location. ``source``
#: and ``file_path`` are accepted for continuity with existing instance configs.
SOURCE_KEYS = ("source_path", "source", "file_path")

_NO_SOURCE = (
    "No source configured. Set 'source_path' on the instance, the "
    f"'{cfg.SETTING_SYNC_REMOTE}' setting, or the {cfg.ENV_SYNC_REMOTE} env var."
)


class SharePointPlugin(DataSourcePlugin):
    """SharePoint list / document library data source.

    A SharePoint list is reached as a delimited or Excel export on an
    [rclone](https://rclone.org) remote (``remote:Site/Lists/Name.csv``); a local
    path to the same export is also accepted, which is what tests use. The plugin
    holds no per-call state — every method takes the instance config.

    Args:
        provider: Object exposing ``cat(target, max_bytes=None, timeout_sec=...)``,
            ``open(target)`` and ``list_files(target, recursive=...)``. Defaults to
            ``scidk.core.providers.RcloneProvider``. Injectable so the contract can
            be exercised without a live SharePoint list.
    """

    name = "sharepoint"
    display_name = "SharePoint Lists"
    source_types = ["sharepoint_list", "sharepoint_library"]

    def __init__(self, provider: Optional[Any] = None):
        self._provider = provider

    # ------------------------------------------------------------ config

    def resolve_source(self, config: Dict[str, Any]) -> str:
        """Resolve the source location from the instance config, then settings.

        Precedence: an explicit instance key (see :data:`SOURCE_KEYS`), then the
        persisted setting, then the environment variable — the standard SciDK
        order. Returns "" when nothing is configured.
        """
        for key in SOURCE_KEYS:
            value = str((config or {}).get(key) or "").strip()
            if value:
                return value
        return str(cfg.get_config_value(cfg.SETTING_SYNC_REMOTE, cfg.ENV_SYNC_REMOTE) or "").strip()

    @staticmethod
    def _timeout(config: Dict[str, Any]) -> float:
        """Fetch timeout in seconds for buffered reads (default 120)."""
        try:
            return float((config or {}).get("timeout_sec", ingest.DEFAULT_TIMEOUT_SEC))
        except (TypeError, ValueError):
            return ingest.DEFAULT_TIMEOUT_SEC

    # ------------------------------------------------------- FAIR: Findable

    def find(self, config: Dict[str, Any]) -> FindResult:
        """Discover the list's columns, row count and a small sample.

        One lazy pass over the source, retaining only the sample rows, so this
        stays inside its 10s budget and flat in memory. An exact ``row_count``
        needs the whole source; past ``ingest.MAX_SCAN_ROWS`` it gives up and
        reports None with ``metadata["row_count_truncated"]`` set.

        Args:
            config: Instance configuration. Keys: a source key (see
                :data:`SOURCE_KEYS`), optional ``sheet`` (Excel worksheet name),
                ``sample_rows`` (default 3), ``timeout_sec``.

        Returns:
            FindResult: never raises — an unreachable source is ``ok: False``
            with the reason in ``error``.
        """
        source = self.resolve_source(config)
        empty: FindResult = {"ok": False, "columns": [], "row_count": None,
                             "sample": [], "metadata": {}}
        if not source:
            return {**empty, "error": _NO_SOURCE}

        try:
            sample_rows = max(0, int((config or {}).get("sample_rows", 3)))
        except (TypeError, ValueError):
            sample_rows = 3

        metadata = ingest.source_metadata(source, provider=self._provider)
        metadata["source_path"] = source
        try:
            scan = ingest.scan_source(
                source,
                provider=self._provider,
                timeout_sec=self._timeout(config),
                sample_rows=sample_rows,
                sheet=(config or {}).get("sheet"),
            )
        except Exception as e:  # noqa: BLE001 - discovery failure is a result
            logger.warning("SharePoint find() failed for %r: %s", source, e)
            return {**empty, "metadata": metadata, "error": str(e)}

        if scan["truncated"]:
            metadata["row_count_truncated"] = True
        return {
            "ok": True,
            "columns": scan["columns"],
            "row_count": scan["row_count"],
            "sample": scan["sample"],
            "metadata": metadata,
            "error": None,
        }

    # ----------------------------------------------------- FAIR: Accessible

    def access(self, config: Dict[str, Any]) -> AccessResult:
        """Verify credentials permit an authenticated read of the list's rows.

        Distinct from :meth:`find`: this reads actual file content, which a
        credential scoped to listing metadata cannot do. It reads only the first
        byte — enough to prove authorization without paying for the transfer.

        Args:
            config: Instance configuration, as for :meth:`find`.

        Returns:
            AccessResult: never raises — a rejected credential is ``ok: False``
            with the provider's message in ``error``.
        """
        source = self.resolve_source(config)
        if not source:
            return {"ok": False, "auth_method": None, "error": _NO_SOURCE}
        auth_method = ingest.detect_auth_method(source)
        try:
            ingest.verify_read(source, provider=self._provider, timeout_sec=self._timeout(config))
        except Exception as e:  # noqa: BLE001 - a rejected credential is a result
            logger.info("SharePoint access() denied for %r: %s", source, e)
            return {"ok": False, "auth_method": auth_method, "error": str(e)}
        return {"ok": True, "auth_method": auth_method, "error": None}

    # -------------------------------------------------- FAIR: Interoperable

    def fetch(self, config: Dict[str, Any]) -> Iterator[Dict[str, Any]]:
        """Stream the list's rows lazily as raw ``{column: value}`` dicts.

        Values are raw strings exactly as exported — no transforms, no coercion,
        no renaming. Translating them is the Pipeline's job, driven by a mapping
        config, which is what keeps the same row stream reusable for any target
        schema.

        Args:
            config: Instance configuration, as for :meth:`find`.

        Returns:
            An iterator of rows. Delimited sources stream from a pipe and never
            hold more than a row at a time; a remote Excel workbook is buffered
            first because a zip container needs random access.

        Raises:
            ValueError: No source is configured. Raised eagerly, not on first
                iteration, so a misconfiguration surfaces where it happened.
        """
        source = self.resolve_source(config)
        if not source:
            raise ValueError(_NO_SOURCE)
        return ingest.iter_rows(
            source,
            provider=self._provider,
            timeout_sec=self._timeout(config),
            sheet=(config or {}).get("sheet"),
        )

    # ----------------------------------------------------- FAIR: Reproducible

    def transform_library(self) -> Dict[str, Callable]:
        """Return the six SharePoint-specific transforms, by name.

        Source-agnostic transforms are not included — those live in
        :mod:`scidk.pipeline.transforms` and the Pipeline always provides them.
        Every entry is a pure function, so a mapping config plus this library
        fully determines a run's output.
        """
        return dict(SHAREPOINT_TRANSFORMS)
