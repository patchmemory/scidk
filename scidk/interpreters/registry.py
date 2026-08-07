"""Registry and dispatch for :class:`~scidk.interpreters.base.BaseInterpreter`.

Answers two questions for :mod:`scidk.services.enrichment_service`: given a file,
which interpreter reads it, and given a directory, which interpreter summarises
it.

Not to be confused with :class:`scidk.core.registry.InterpreterRegistry`, which
serves the older duck-typed scan-time interpreters. This one is named
:class:`BaseInterpreterRegistry` so the two never get imported under the same
name by accident. They share no state and no contract.

``KNOWN_INTERPRETERS`` is read from the standalone scanner
(``tools/scidk_scanner.py``) so that the extensions the scanner labels and the
extensions we can actually interpret can be compared — see
:func:`coverage_gaps`. Note the scanner uses its own id namespace
(``csv_interpreter``, ``python_interpreter``) that does not match either
registry's ids; it is a label the scanner writes into
``files.interpreted_as``, not a resolvable interpreter name. Dispatch here is by
extension via :meth:`BaseInterpreter.can_handle`, never by that string.
"""
from __future__ import annotations

import importlib
import importlib.util
import logging
from pathlib import Path
from typing import Dict, List, Optional

from .base import BaseInterpreter

logger = logging.getLogger(__name__)

#: Mirror of ``tools/scidk_scanner.py``'s table, used only when that file cannot
#: be imported (e.g. an installed wheel that ships ``scidk/`` but not ``tools/``).
#: Keep in step with the scanner when adding an extension there.
_KNOWN_INTERPRETERS_FALLBACK: Dict[str, str] = {
    ".csv": "csv_interpreter",
    ".tsv": "csv_interpreter",
    ".xlsx": "xlsx_interpreter",
    ".xls": "xlsx_interpreter",
    ".json": "json_interpreter",
    ".jsonl": "json_interpreter",
    ".yaml": "yaml_interpreter",
    ".yml": "yaml_interpreter",
    ".ipynb": "ipynb_interpreter",
    ".dcm": "dicom_interpreter",
    ".dicom": "dicom_interpreter",
    ".tif": "ome_tiff_interpreter",
    ".tiff": "ome_tiff_interpreter",
    ".h5": "hdf5_interpreter",
    ".hdf5": "hdf5_interpreter",
    ".nc": "netcdf_interpreter",
    ".nc4": "netcdf_interpreter",
    ".rdf": "rdf_interpreter",
    ".ttl": "rdf_interpreter",
    ".owl": "owl_interpreter",
    ".py": "python_interpreter",
}


def _load_known_interpreters() -> Dict[str, str]:
    """Return the scanner's extension→label map, falling back to a local copy.

    ``tools/`` is not a package (no ``__init__.py``) and is not installed with
    ``scidk``, so this tries the namespace-package import first and then a
    direct load by file path from the repo root. The scanner guards its entry
    point with ``if __name__ == "__main__"``, so importing it runs no work.
    """
    try:
        module = importlib.import_module("tools.scidk_scanner")
        return dict(module.KNOWN_INTERPRETERS)
    except Exception:
        pass

    try:
        # scidk/interpreters/registry.py -> repo root is three parents up.
        scanner_path = Path(__file__).resolve().parents[2] / "tools" / "scidk_scanner.py"
        if scanner_path.is_file():
            spec = importlib.util.spec_from_file_location("_scidk_scanner", scanner_path)
            if spec and spec.loader:
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                return dict(module.KNOWN_INTERPRETERS)
    except Exception as exc:
        logger.debug("Could not load KNOWN_INTERPRETERS from scanner: %s", exc)

    return dict(_KNOWN_INTERPRETERS_FALLBACK)


#: Extension → scanner label. See module docstring on the id namespace.
KNOWN_INTERPRETERS: Dict[str, str] = _load_known_interpreters()


class BaseInterpreterRegistry:
    """Holds registered interpreters and resolves paths to them.

    Registration order is preserved and first match wins, so a more specific
    interpreter must be registered before a more general one claiming the same
    extension.
    """

    def __init__(self) -> None:
        self._file: List[BaseInterpreter] = []
        self._directory: List[BaseInterpreter] = []

    def register(self, interpreter: BaseInterpreter) -> BaseInterpreter:
        """Add an interpreter, routed by its ``dispatch`` attribute.

        Re-registering the same ``name`` replaces the earlier instance, which
        keeps module reloads and repeated ``register_builtins`` calls idempotent.
        """
        dispatch = getattr(interpreter, "dispatch", "file")
        bucket = self._directory if dispatch == "directory" else self._file
        name = getattr(interpreter, "name", None)
        for idx, existing in enumerate(bucket):
            if getattr(existing, "name", None) == name:
                bucket[idx] = interpreter
                return interpreter
        bucket.append(interpreter)
        return interpreter

    def get_interpreter_for_file(self, path: Path) -> Optional[BaseInterpreter]:
        """First file-dispatch interpreter whose ``can_handle`` accepts ``path``."""
        for interpreter in self._file:
            try:
                if interpreter.can_handle(path):
                    return interpreter
            except Exception as exc:
                logger.debug("can_handle failed for %s on %s: %s",
                             getattr(interpreter, "name", "?"), path, exc)
        return None

    def get_interpreter_for_directory(self, path: Path) -> Optional[BaseInterpreter]:
        """First directory-dispatch interpreter whose ``can_handle`` accepts ``path``.

        Directory ``can_handle`` implementations call ``iterdir()``, which raises
        on an unreadable or vanished directory; that is caught here so a single
        permission error cannot end a pass.
        """
        for interpreter in self._directory:
            try:
                if interpreter.can_handle(path):
                    return interpreter
            except Exception as exc:
                logger.debug("can_handle failed for %s on %s: %s",
                             getattr(interpreter, "name", "?"), path, exc)
        return None

    def get(self, name: str) -> Optional[BaseInterpreter]:
        """Look an interpreter up by its ``name``, across both dispatch kinds."""
        for interpreter in self._file + self._directory:
            if getattr(interpreter, "name", None) == name:
                return interpreter
        return None

    def all(self) -> List[BaseInterpreter]:
        return list(self._file) + list(self._directory)

    def file_interpreters(self) -> List[BaseInterpreter]:
        return list(self._file)

    def directory_interpreters(self) -> List[BaseInterpreter]:
        return list(self._directory)

    def file_extensions(self) -> List[str]:
        """Every extension claimed by a file-dispatch interpreter, lowercased.

        The enrichment service uses this to select candidates by extension,
        which is what makes it possible to enrich files indexed before their
        interpreter existed (their ``interpreted_as`` is null).
        """
        exts = []
        for interpreter in self._file:
            for ext in getattr(interpreter, "extensions", []):
                lowered = ext.lower()
                if lowered not in exts:
                    exts.append(lowered)
        return exts

    def coverage_gaps(self) -> Dict[str, str]:
        """Extensions the scanner labels but no registered interpreter reads.

        The scanner's table promises ``hdf5_interpreter`` for ``.h5`` and three
        others that have never been implemented, so a coverage report built from
        ``interpreted_as`` alone overstates what can actually be enriched.
        """
        covered = set(self.file_extensions())
        return {ext: label for ext, label in KNOWN_INTERPRETERS.items()
                if ext.lower() not in covered}


#: Process-wide registry. Import this, not a new instance.
registry = BaseInterpreterRegistry()

_builtins_registered = False


def register_builtins(target: Optional[BaseInterpreterRegistry] = None) -> BaseInterpreterRegistry:
    """Register the interpreters that ship with SciDK.

    Imports are deferred into the function body because the interpreter modules
    import :mod:`scidk.interpreters.base`, and several of them will want the
    registry itself; importing them at module scope would be circular.

    Imports here are deliberately unguarded: an interpreter that fails to import
    should surface as an error, not silently vanish from every enrichment run.
    """
    global _builtins_registered
    target = target if target is not None else registry

    interpreter_classes: tuple = ()

    for interpreter_class in interpreter_classes:
        target.register(interpreter_class())

    if target is registry:
        _builtins_registered = True
    return target


def ensure_registered() -> BaseInterpreterRegistry:
    """Register the built-ins once, then return the shared registry."""
    if not _builtins_registered:
        register_builtins(registry)
    return registry


def get_interpreter_for_file(path: Path) -> Optional[BaseInterpreter]:
    """Module-level shorthand for ``ensure_registered().get_interpreter_for_file``."""
    return ensure_registered().get_interpreter_for_file(path)


def get_interpreter_for_directory(path: Path) -> Optional[BaseInterpreter]:
    """Module-level shorthand for ``ensure_registered().get_interpreter_for_directory``."""
    return ensure_registered().get_interpreter_for_directory(path)
