"""The interpreter contract for enrichment-dispatched interpreters.

This is the typed contract used by :mod:`scidk.services.enrichment_service`. It
is deliberately separate from the older duck-typed interpreters registered in
``scidk/interpreters/__init__.py`` (``INTERPRETERS``), which have a different
signature — ``interpret(path)`` returning a ``{'status', 'data', ...}`` dict —
and are dispatched inline during a scan by :class:`scidk.core.registry.InterpreterRegistry`.

The two contracts coexist on purpose. The legacy one runs during a scan and
writes to SQLite; this one runs after a scan, off the graph, and writes typed
domain nodes. Mixing a :class:`BaseInterpreter` into the legacy ``INTERPRETERS``
list would break the scan path, and vice versa.

The one hard rule here is that :meth:`BaseInterpreter.interpret` never raises.
Enrichment runs unattended over millions of files; one malformed header must
degrade to a ``confidence="stub"`` result carrying a warning, not abort a batch.
Use :func:`stub_result` for that case.
"""
from dataclasses import dataclass, field
from typing import Optional
from pathlib import Path
from abc import ABC, abstractmethod


@dataclass
class InterpretationResult:
    node_type: str        # e.g. "FlowCytometrySession", "HistologySlide"
    node_label: str       # human-readable
    confidence: str       # "confirmed" | "inferred" | "stub"
    properties: dict
    provenance_edges: list[dict]  # DERIVED_FROM, USED, etc.
    warnings: list[str] = field(default_factory=list)
    raw_metadata: Optional[dict] = None


class BaseInterpreter(ABC):
    name: str
    dispatch: str         # "file" | "directory"
    extensions: list[str]

    def can_handle(self, path: Path) -> bool:
        return path.suffix.lower() in [e.lower() for e in self.extensions]

    @abstractmethod
    def interpret(self, path: Path, context: dict) -> InterpretationResult:
        """Never raise. Always return a result, even a stub."""
        ...


#: Confidence levels, in descending order of trust.
#:
#: ``confirmed`` — read out of the file's own metadata.
#: ``inferred``  — derived from filename, directory shape or sibling files.
#: ``stub``      — the file could not be read; the node records only that it exists.
CONFIDENCE_CONFIRMED = "confirmed"
CONFIDENCE_INFERRED = "inferred"
CONFIDENCE_STUB = "stub"


def stub_result(node_type: str, path: Path, reason: str) -> InterpretationResult:
    """Build the minimal result for a file that could not be read.

    Every interpreter needs this in its exception handler, so it lives here
    rather than being reimplemented four times. The node still carries
    ``source_path`` so a later re-run can find and upgrade it in place.

    Args:
        node_type: The label this interpreter would have emitted on success.
        path: The file or directory that failed.
        reason: Short description of what went wrong, recorded as a warning.
    """
    return InterpretationResult(
        node_type=node_type,
        node_label=path.name,
        confidence=CONFIDENCE_STUB,
        properties={"source_path": str(path), "name": path.name},
        provenance_edges=[],
        warnings=[reason],
    )
