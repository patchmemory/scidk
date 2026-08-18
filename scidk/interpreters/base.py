"""The interpreter contract, written down.

Eleven interpreters existed before this file and none of them shared a base
class: the contract was "return a dict with ``status``/``data``/``nodes``/
``relationships``", enforced by nothing and discoverable only by reading an
existing interpreter. :class:`BaseInterpreter` is that contract made explicit,
plus the two things the duck-typed shape could not express — a ``dispatch``
kind, so a directory-level interpreter is distinguishable from a file-level
one, and a ``context`` argument, so an interpreter can see its siblings.

Existing interpreters are deliberately **not** retrofitted. They keep working
untouched; the ABC is the shape new ones take.

Two details make both worlds coexist:

* ``interpret(path, context=None)`` — the four legacy call sites
  (``core/filesystem.py``, ``web/routes/api_files.py`` ×2,
  ``services/scans_service.py``) call ``interp.interpret(path)`` with one
  argument. Context is therefore optional, not required.
* :class:`InterpretationResult` answers ``.get()`` and ``[...]`` by delegating
  to :meth:`~InterpretationResult.to_legacy_dict`. Those same call sites read
  ``result.get('status')``, ``result.get('nodes')`` and friends. Without this
  a new interpreter selected by extension during an ordinary scan would return
  an object the scan path cannot read, and — because every one of those sites
  wraps the call in ``except Exception`` — the failure would be recorded as a
  parse error rather than raised. Quacking like the legacy dict is cheaper than
  four edits and keeps one code path instead of two.

``id`` versus ``name``: the registry keys interpreters on the ``id`` class
attribute (``core/registry.py:register_extension``), and
``scanner_formats.KNOWN_INTERPRETERS`` values are those ids. ``name`` is the
human-readable display string every existing interpreter already carries
("OME-TIFF Interpreter"). Both are declared below and the convention is kept:
**``id`` is the registry key.**
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

__all__ = ["InterpretationResult", "BaseInterpreter"]

#: Values ``confidence`` may take. ``stub`` means interpretation failed and the
#: result exists only to record why — it is mapped to an ``error`` status on the
#: way into the legacy envelope so the commit pipeline does not treat a failure
#: as a successful read.
CONFIDENCE_LEVELS = ("confirmed", "inferred", "stub")


@dataclass
class InterpretationResult:
    """One domain node an interpreter declares, plus how sure it is.

    ``properties`` must contain ``source_path``: it is the key property of the
    declared node, and ``write_declared_nodes`` rejects a declaration whose
    ``key_property`` is absent from ``properties``.
    """

    node_type: str                                    # KG label, e.g. "FlowCytometrySession"
    node_label: str                                   # human-readable display name
    confidence: str                                   # "confirmed" | "inferred" | "stub"
    properties: Dict[str, Any]
    provenance_edges: List[Dict[str, Any]]            # DERIVED_FROM, METADATA_SOURCE, …
    warnings: List[str] = field(default_factory=list)
    raw_metadata: Optional[Dict[str, Any]] = None

    def to_legacy_dict(self) -> Dict[str, Any]:
        """Bridge to the dict shape the commit pipeline already reads.

        ``nodes`` and ``relationships`` are siblings of ``data`` because that is
        where ``commit_service.extract_declared_nodes_from_scan`` looks for
        them; see ``core/interpreter_persistence.build_payload``.

        A stub declares no node. It records that interpretation was attempted
        and why it failed — writing an ``UnknownFile`` per unreadable file would
        put the failures in the graph as if they were findings.
        """
        data = dict(self.properties)
        if self.warnings:
            # build_payload keeps only status/data/nodes/relationships, so a
            # warning that is not inside `data` is discarded on the way to
            # SQLite and to the Interpretation node.
            data['warnings'] = list(self.warnings)

        if self.confidence == 'stub':
            return {'status': 'error', 'data': data, 'nodes': [], 'relationships': []}

        properties = dict(self.properties)
        properties.setdefault('source_path', '')
        properties['confidence'] = self.confidence

        return {
            'status': 'success',
            'data': data,
            'nodes': [{
                'label': self.node_type,
                'key_property': 'source_path',
                'properties': properties,
            }],
            'relationships': list(self.provenance_edges),
        }

    # -- dict-compatible reads, for the pre-ABC call sites -------------------
    def get(self, key: str, default: Any = None) -> Any:
        return self.to_legacy_dict().get(key, default)

    def __getitem__(self, key: str) -> Any:
        return self.to_legacy_dict()[key]

    def __contains__(self, key: str) -> bool:
        return key in self.to_legacy_dict()


class BaseInterpreter(ABC):
    """ABC for SciDK interpreters.

    New interpreters subclass this. Existing ones are not required to — the
    enrichment dispatcher works with both, and the registry only ever asks for
    ``id``, ``extensions`` and ``interpret``.
    """

    id: str = ''                    # registry key; matches a KNOWN_INTERPRETERS value
    name: str = ''                  # human-readable display name
    version: str = '1.0.0'
    dispatch: str = 'file'          # "file" | "directory"
    extensions: List[str] = []      # for "file" dispatch; empty for "directory"
    default_enabled: bool = True

    def can_handle(self, path: Path, context: Optional[dict] = None) -> bool:
        """True if this interpreter should handle this path. Never raises.

        Default is an extension check. Directory interpreters must override it —
        with ``extensions = []`` the default answers False for everything.
        """
        try:
            return path.suffix.lower() in [e.lower() for e in self.extensions]
        except Exception:
            return False

    @abstractmethod
    def interpret(self, path: Path, context: Optional[dict] = None) -> InterpretationResult:
        """Run the interpreter. Must never raise — return a stub instead.

        ``context`` is absent when called from the ordinary scan path. When the
        enrichment dispatcher calls it, the dict may contain:

        - ``sibling_files``: ``list[str]`` — filenames in the same directory
        - ``sibling_interpretations``: ``dict[str, InterpretationResult]`` —
          results from file-level interpreters already run on siblings
          (directory interpreters only; may be empty on the first pass)
        - ``host``: ``str`` — the storage host identifier
        - ``scan_id``: ``str``
        """
        ...

    @staticmethod
    def _file_match(path: Path, context: Optional[dict]) -> Dict[str, Any]:
        """Key for MATCHing the ``:File`` this interpretation came from.

        ``:File`` is identified by ``(path, host)`` and the only index on it is
        the composite ``file_identity`` over both. A composite index needs every
        property in the pattern, so matching on ``path`` alone is a full label
        scan — 3.72s against 5.5M File nodes versus 0.01s with the host. The
        dispatcher puts the scan's host in ``context`` precisely so an edge can
        be written against the indexed key; without a context, path alone is
        still correct, just slow.
        """
        match: Dict[str, Any] = {'path': str(path)}
        host = (context or {}).get('host')
        if host:
            match['host'] = host
        return match

    def _stub(self, path: Path, warning: str) -> InterpretationResult:
        """A minimal result recording why interpretation did not happen."""
        return InterpretationResult(
            node_type='UnknownFile',
            node_label=path.name,
            confidence='stub',
            properties={'source_path': str(path)},
            provenance_edges=[],
            warnings=[warning],
        )
