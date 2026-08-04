"""Cypher identifier guards for everything the Pipeline writes.

:meth:`~scidk.services.neo4j_client.Neo4jClient.write_declared_nodes`
parameterizes property *values* but interpolates labels, relationship types and
property *names* straight into the query string (``neo4j_client.py:263``). A
mapping config is user-authored, so every identifier it names has to be checked
before it reaches Cypher: a mapped property called ``Sample ID`` is a syntax
error swallowed into ``result['errors']``, and a hostile one is an injection.

These are the same guards ``canvas_service`` has always applied to labels and
relationship types — moved here so the canvas and the Pipeline share one
definition — extended to property keys, the case the canvas never had to handle
because it only ever writes ``name``.

Validation is deliberately a whitelist, not an escape. Neo4j does support
arbitrary identifiers via backtick quoting, but ``write_declared_nodes`` does not
quote, and inventing an escaping layer here would leave two disagreeing notions
of what a legal identifier is. A config naming ``Sample ID`` is a config to fix,
not a string to mangle.
"""
from __future__ import annotations

import re
from typing import Optional

__all__ = [
    "IdentifierError",
    "LABEL_RE",
    "PROPERTY_RE",
    "REL_RE",
    "check_identifier",
    "require_identifier",
]

#: A Cypher identifier safe to interpolate unquoted: leading letter or
#: underscore, then letters, digits and underscores. Labels, relationship types
#: and property keys all share it.
_IDENTIFIER_RE = re.compile(r'^[A-Za-z_][A-Za-z0-9_]*$')

#: Aliases, so call sites read as what they are guarding.
LABEL_RE = _IDENTIFIER_RE
REL_RE = _IDENTIFIER_RE
PROPERTY_RE = _IDENTIFIER_RE


class IdentifierError(ValueError):
    """An identifier from a mapping config is not safe to interpolate."""


def check_identifier(value: object, kind: str = "identifier") -> Optional[str]:
    """Return a human-readable reason ``value`` is unusable, or None if it is fine.

    Args:
        value: The candidate label, relationship type or property key.
        kind: What it is, for the message ("label", "relationship type", ...).

    Returns:
        None when ``value`` is a valid identifier, otherwise a message naming the
        offending value — suitable for a validation report the user reads.
    """
    if value is None or (isinstance(value, str) and not value.strip()):
        return f"{kind} is missing"
    if not isinstance(value, str):
        return f"{kind} must be a string, got {type(value).__name__}"
    if not _IDENTIFIER_RE.match(value):
        return (
            f"{kind} {value!r} is not a valid Cypher identifier "
            "(letters, digits and underscore only; must not start with a digit)"
        )
    return None


def require_identifier(value: object, kind: str = "identifier") -> str:
    """Return ``value`` unchanged, or raise :class:`IdentifierError`.

    For the write path, where an unchecked identifier must never get through.
    Prefer :func:`check_identifier` when collecting a validation report.
    """
    problem = check_identifier(value, kind)
    if problem:
        raise IdentifierError(problem)
    return str(value)
