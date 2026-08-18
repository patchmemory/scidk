"""Interpreter lookup by id, with no Flask app required.

``core/registry.InterpreterRegistry`` is the app-scoped registry: it is built
during ``create_app()``, carries the rule engine and the enable/disable state,
and lives on ``app.extensions['scidk']['registry']``. That is the right object
inside a request.

The enrichment dispatcher also runs as ``python -m
scidk.services.enrichment_service``, where there is no app and nothing has
called ``register_all()``. This module is the id → instance map derived
straight from :data:`scidk.interpreters.INTERPRETERS`, so both entry points
resolve the same ids to the same classes.

Instances are cached because interpreters are stateless by convention and the
dispatcher asks for the same one once per file.
"""
from __future__ import annotations

from typing import Dict, List, Optional

__all__ = ["get_interpreter_by_id", "list_interpreter_ids", "clear_cache"]

_INSTANCES: Dict[str, object] = {}


def _build() -> Dict[str, object]:
    if _INSTANCES:
        return _INSTANCES
    from . import INTERPRETERS
    for interp_class in INTERPRETERS:
        interpreter_id = getattr(interp_class, 'id', None)
        if not interpreter_id:
            continue
        try:
            _INSTANCES[interpreter_id] = interp_class()
        except Exception:
            # A constructor that fails (a missing optional dependency imported
            # at __init__ time, say) must not take every other interpreter with
            # it — the dispatcher would then silently process nothing.
            continue
    return _INSTANCES


def get_interpreter_by_id(interpreter_id: Optional[str]) -> Optional[object]:
    """Instance for a registry id, or None if nothing claims it.

    None is the normal answer for ids that name interpreters which do not exist
    yet: ``scanner_formats`` deliberately records ``mtx_interpreter`` and
    friends against patterns the scanner can already detect.
    """
    if not interpreter_id:
        return None
    return _build().get(interpreter_id)


def list_interpreter_ids() -> List[str]:
    """Every registered id, sorted. Useful for validating a ``--interpreter``."""
    return sorted(_build().keys())


def clear_cache() -> None:
    """Drop cached instances. For tests that reload interpreter modules."""
    _INSTANCES.clear()
