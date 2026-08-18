"""The ``DataSourcePlugin`` contract.

Every SciDK data source plugin implements this interface and nothing more. The
Pipeline calls these four methods; the plugin never writes to the graph.

FAIR mapping
------------
The four methods correspond to the FAIR principles, which is why the contract has
exactly this shape:

===================== ================= ==========================================
Method                FAIR principle    Responsibility
===================== ================= ==========================================
``find()``            **F**indable      Discover what the source contains —
                                        columns, row count, a small sample. Cheap
                                        and bounded; must complete in <10s.
``access()``          **A**ccessible    Verify that credentials permit a full,
                                        authenticated read of the source, and
                                        report which auth method was used.
``fetch()``           **I**nteroperable Stream the source as raw ``dict`` rows —
                                        one neutral representation the Pipeline
                                        can translate into any target schema. No
                                        transforms are applied here.
``transform_library`` **R**eproducible  Publish the source-specific, documented,
                                        pure field transforms a mapping config may
                                        name. Pure functions, so a run is
                                        reproducible from config alone.
===================== ================= ==========================================

What a plugin does NOT own
--------------------------
Column→node mapping, relationship construction, label/property sanitization,
``write_declared_nodes`` calls, FAIR check / dry-run reporting, scheduling, and
run history all belong to :mod:`scidk.pipeline`. A plugin that reaches for
``Neo4jClient`` is doing the Pipeline's job.

Deployment-specific mapping lives in a mapping config JSON (for example
``plugins/sharepoint_intake/configs/aipt_intake_mapping.json``), which the
Pipeline reads — not the plugin.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Callable, Dict, Iterator, List, Optional, TypedDict


class FindResult(TypedDict, total=False):
    """Return shape of :meth:`DataSourcePlugin.find`.

    Keys:
        ok: True when discovery succeeded.
        columns: Column/field names present in the source, in source order.
        row_count: Total rows, or None when counting would be unbounded.
        sample: A few fully-formed raw rows (typically 3) for UI preview.
        metadata: Source-specific detail (size, mtime, transport, sheet, ...).
        error: Human-readable failure reason; None/absent when ``ok`` is True.
    """

    ok: bool
    columns: List[str]
    row_count: Optional[int]
    sample: List[Dict[str, Any]]
    metadata: Dict[str, Any]
    error: Optional[str]


class AccessResult(TypedDict, total=False):
    """Return shape of :meth:`DataSourcePlugin.access`.

    Keys:
        ok: True when an authenticated full read of the source is permitted.
        auth_method: Identifier of the credential type actually used, e.g.
            ``"rclone_oauth"``, ``"rclone_basic"``, ``"local"``; None when it
            could not be determined.
        error: Human-readable failure reason; None/absent when ``ok`` is True.
    """

    ok: bool
    auth_method: Optional[str]
    error: Optional[str]


class DataSourcePlugin(ABC):
    """Base class for SciDK data source plugins.

    Subclasses set the three class attributes and implement the four methods.
    Every method takes a plain ``config`` dict (the instance configuration
    persisted by the Pipeline) so plugins stay stateless between calls.

    Attributes:
        name: Stable machine identifier, e.g. ``"sharepoint"``.
        display_name: Human-readable name shown in the UI.
        source_types: Source type identifiers this plugin can serve, e.g.
            ``["sharepoint_list", "sharepoint_library"]``.
    """

    name: str = ""
    display_name: str = ""
    source_types: List[str] = []

    @abstractmethod
    def find(self, config: Dict[str, Any]) -> FindResult:
        """FAIR: **Findable**. Discover the shape of the source.

        Args:
            config: Instance configuration. Must carry enough to locate the
                source (e.g. ``{"source_path": "remote:Site/Lists/Name"}``).

        Returns:
            FindResult: columns, row count (or None), and a small sample.

        Must be cheap and bounded — target under 10 seconds — and must not raise
        for an unreachable or malformed source; report it via ``ok``/``error``.
        """

    @abstractmethod
    def access(self, config: Dict[str, Any]) -> AccessResult:
        """FAIR: **Accessible**. Verify credentials permit a full read.

        Distinct from :meth:`find`: ``find()`` may succeed against a listing or a
        bounded prefix that a restricted credential can still see, while
        ``access()`` asserts that the authenticated data read the Pipeline will
        actually perform is permitted.

        Args:
            config: Instance configuration, as for :meth:`find`.

        Returns:
            AccessResult: ``ok`` plus the auth method used. Never raises for a
            credential failure — that is a result, not an exception.
        """

    @abstractmethod
    def fetch(self, config: Dict[str, Any]) -> Iterator[Dict[str, Any]]:
        """FAIR: **Interoperable**. Stream the source as raw rows.

        Args:
            config: Instance configuration, as for :meth:`find`.

        Yields:
            dict: One row as ``{column_name: raw_value}``. Values are raw — no
            transforms, no coercion, no renaming. Mapping is the Pipeline's job.

        Must stream lazily. Implementations must not materialize the full source
        in memory; the Pipeline relies on this to ingest lists larger than RAM.
        """

    @abstractmethod
    def transform_library(self) -> Dict[str, Callable]:
        """FAIR: **Reproducible**. Publish source-specific named transforms.

        Returns:
            dict: ``{name: callable}`` that a mapping config may reference by
            name. Source-specific transforms only — source-agnostic ones live in
            :mod:`scidk.pipeline.transforms` and are always available. Return an
            empty dict when the plugin adds none.

        Every callable must be a pure function: same input, same output, no I/O.
        """
