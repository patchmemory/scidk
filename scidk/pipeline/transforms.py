"""Core field transforms — source-agnostic, owned by the Pipeline.

These are the transforms every mapping config can name regardless of which plugin
produced the row stream. Source-specific transforms are published separately by
each plugin via ``DataSourcePlugin.transform_library()``.

Contract for every transform in this module and in any plugin transform library:

* **Pure.** No I/O, no clock, no global state. Same input, same output.
* **Empty input is not an error.** ``None``, ``""`` and whitespace-only input
  return the type's empty value (``None`` for scalars, ``[]`` for lists) so a
  blank cell simply omits the property.
* **Malformed input raises** :class:`TransformError`. The Pipeline catches it,
  attributes it to the row and column, and continues — a bad cell must never
  abort a run.

The full mapping engine that resolves these names and applies them lands in
Cycle 3B (``scidk/pipeline/mapping_engine.py``). The implementations here are
deliberately minimal; Cycle 3B owns their final semantics and the registry
lookup that exposes them to mapping configs.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Callable, Dict, List, Optional

__all__ = [
    "CORE_TRANSFORMS",
    "TransformError",
    "boolean_coerce",
    "date_parse",
    "integer_coerce",
    "lowercase_strip",
    "split_delimiter",
]


class TransformError(ValueError):
    """Raised when a transform receives input it cannot meaningfully convert.

    Expected and caught by the Pipeline: it records the offending row/column and
    keeps going. Not a programming error — do not let it escape a run.
    """


# Tokens accepted by :func:`boolean_coerce`, matched case-insensitively.
_TRUE_TOKENS = frozenset({"true", "t", "yes", "y", "1", "on"})
_FALSE_TOKENS = frozenset({"false", "f", "no", "n", "0", "off"})

# Formats tried by :func:`date_parse`, in order. ISO-8601 is handled separately.
_DATE_FORMATS = (
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d",
    "%m/%d/%Y %H:%M:%S",
    "%m/%d/%Y %H:%M",
    "%m/%d/%Y",
    "%d/%m/%Y",
    "%m/%d/%y",
    "%Y/%m/%d",
    "%d-%b-%Y",
    "%b %d, %Y",
)


def _as_text(value: Any, transform: str) -> Optional[str]:
    """Return ``value`` as a stripped string, or None when it is empty.

    Rejects containers — a transform is a *field* transform, so a list or dict
    reaching one means the mapping config pointed it at the wrong thing.
    """
    if value is None:
        return None
    if isinstance(value, (list, tuple, set, dict)):
        raise TransformError(f"{transform}: expected a scalar, got {type(value).__name__}")
    text = value.strip() if isinstance(value, str) else str(value).strip()
    return text or None


def lowercase_strip(value: Any) -> Optional[str]:
    """Strip surrounding whitespace and lowercase.

    Args:
        value: Any scalar.

    Returns:
        The normalized string, or None when the input is empty.
    """
    text = _as_text(value, "lowercase_strip")
    return text.lower() if text is not None else None


def integer_coerce(value: Any) -> Optional[int]:
    """Coerce to ``int``.

    Accepts integral floats and numeric strings, including thousands separators
    (``"1,234"``) and integral decimals (``"12.0"``).

    Args:
        value: Any scalar.

    Returns:
        The integer, or None when the input is empty.

    Raises:
        TransformError: The value is not an integer.
    """
    if isinstance(value, bool):
        return int(value)
    text = _as_text(value, "integer_coerce")
    if text is None:
        return None
    cleaned = text.replace(",", "").replace("_", "")
    try:
        return int(cleaned)
    except ValueError:
        pass
    try:
        as_float = float(cleaned)
    except ValueError:
        raise TransformError(f"integer_coerce: {text!r} is not an integer") from None
    if as_float != int(as_float):
        raise TransformError(f"integer_coerce: {text!r} is not an integer")
    return int(as_float)


def boolean_coerce(value: Any) -> Optional[bool]:
    """Coerce a boolean-ish token to ``bool``.

    Accepted (case-insensitive): true/t/yes/y/1/on and false/f/no/n/0/off.

    Args:
        value: Any scalar.

    Returns:
        The boolean, or None when the input is empty.

    Raises:
        TransformError: The token is not recognizably boolean.
    """
    if isinstance(value, bool):
        return value
    text = _as_text(value, "boolean_coerce")
    if text is None:
        return None
    token = text.lower()
    if token in _TRUE_TOKENS:
        return True
    if token in _FALSE_TOKENS:
        return False
    raise TransformError(f"boolean_coerce: {text!r} is not a boolean")


def date_parse(value: Any) -> Optional[str]:
    """Parse a date/datetime into an ISO-8601 string.

    A value carrying no time component yields a plain ``YYYY-MM-DD`` date.

    Args:
        value: A ``date``, ``datetime``, or date-like string.

    Returns:
        The ISO-8601 string, or None when the input is empty.

    Raises:
        TransformError: The value is not a recognizable date.
    """
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    text = _as_text(value, "date_parse")
    if text is None:
        return None
    try:
        # Python 3.11+ fromisoformat accepts a trailing "Z" and most ISO shapes.
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        parsed = None
    if parsed is not None:
        # ":" is the tell for a time component; "2024-03-15" is a date, not midnight.
        return parsed.isoformat() if ":" in text else parsed.date().isoformat()
    for fmt in _DATE_FORMATS:
        try:
            parsed = datetime.strptime(text, fmt)
        except ValueError:
            continue
        if "%H" not in fmt:
            return parsed.date().isoformat()
        return parsed.isoformat()
    raise TransformError(f"date_parse: {text!r} is not a recognizable date")


def split_delimiter(value: Any, delimiter: str = ";") -> List[str]:
    """Split a delimited cell into a list of non-empty, stripped tokens.

    Args:
        value: Any scalar. A list/tuple is passed through (already split).
        delimiter: The separator. Must be a non-empty string.

    Returns:
        The tokens, or ``[]`` when the input is empty.

    Raises:
        TransformError: ``delimiter`` is empty.
    """
    if not delimiter:
        raise TransformError("split_delimiter: delimiter must be a non-empty string")
    if isinstance(value, (list, tuple)):
        return [str(v).strip() for v in value if str(v).strip()]
    text = _as_text(value, "split_delimiter")
    if text is None:
        return []
    return [token.strip() for token in text.split(delimiter) if token.strip()]


#: Name → callable registry the mapping engine resolves transform names against.
CORE_TRANSFORMS: Dict[str, Callable] = {
    "lowercase_strip": lowercase_strip,
    "integer_coerce": integer_coerce,
    "boolean_coerce": boolean_coerce,
    "date_parse": date_parse,
    "split_delimiter": split_delimiter,
}
