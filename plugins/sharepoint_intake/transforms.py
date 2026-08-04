"""SharePoint-specific field transforms.

Pure functions, no Flask / Neo4j / rclone imports, so they are unit-testable in
isolation and safe to call from the Pipeline's mapping engine.

These are the transforms a mapping config may name that only make sense for a
SharePoint list export: RFC 5322 "archived" people columns, multi-choice columns,
SharePoint's date and Yes/No renderings, and the ``_sp`` / ``_orig`` column pair
convention left behind by the Drupal→SharePoint migration.

Source-agnostic transforms (``lowercase_strip``, ``integer_coerce``,
``boolean_coerce``, ``date_parse``, ``split_delimiter``) are *not* here — they
live in :mod:`scidk.pipeline.transforms` and the Pipeline always makes them
available.

Contract (shared with the core transforms):

* Empty input (``None`` / ``""`` / whitespace) returns the empty value for the
  type — ``None`` for scalars, ``[]`` for lists. Never an error: a blank
  SharePoint cell just means the property is absent.
* Malformed input raises :class:`~scidk.pipeline.transforms.TransformError`,
  which the Pipeline attributes to the row and column and then continues past.
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Callable, Dict, List, Mapping, Optional

from scidk.pipeline.transforms import TransformError, boolean_coerce, date_parse

__all__ = [
    "SHAREPOINT_TRANSFORMS",
    "TransformError",
    "parse_rfc5322",
    "parse_rfc5322_list",
    "sp_colresolution",
    "sp_date",
    "sp_multiselect",
    "sp_yesno",
]

# "Display Name <address>", with optional quotes around the display name.
_ADDRESSEE = re.compile(r'^"?(?P<name>[^"<>]*?)"?\s*<(?P<email>[^<>]*)>$')

# A bare address with no display name.
_BARE_EMAIL = re.compile(r"^[^\s<>@]+@[^\s<>@]+$")

# SharePoint's multi-choice columns arrive as ";#"-wrapped, ";"- or ","-joined.
_MULTISELECT_SPLIT = re.compile(r";#|[;,]")

# Renderings the SharePoint UI/CSV export produces that ISO parsing misses.
_SP_DATE_FORMATS = (
    "%m/%d/%Y %I:%M %p",
    "%m/%d/%Y %I:%M:%S %p",
    "%m/%d/%Y %H:%M",
    "%d/%m/%Y %I:%M %p",
)


def _text(value: Any, transform: str) -> Optional[str]:
    """Return ``value`` as a stripped string, or None when empty."""
    if value is None:
        return None
    if isinstance(value, (list, tuple, set, dict)):
        raise TransformError(f"{transform}: expected a scalar, got {type(value).__name__}")
    text = value.strip() if isinstance(value, str) else str(value).strip()
    return text or None


def parse_rfc5322(value: Any) -> Optional[Dict[str, Optional[str]]]:
    """Parse one RFC 5322-style person into ``{"name", "email"}``.

    Handles the three shapes SharePoint produces in a single column:

    * ``"Jane Smith <jsmith@mit.edu>"`` — an archived plain-text people column.
    * ``"jsmith@mit.edu"`` — an address with no display name.
    * ``"Jane Smith"`` — a raw People-picker display name, no address available.

    Args:
        value: The raw cell value.

    Returns:
        ``{"name": str|None, "email": str|None}`` with the address lowercased, or
        None when the cell is empty.

    Raises:
        TransformError: The value has an unterminated or empty ``<...>``.
    """
    text = _text(value, "parse_rfc5322")
    if text is None:
        return None

    match = _ADDRESSEE.match(text)
    if match:
        email = match.group("email").strip().lower()
        if not email:
            raise TransformError(f"parse_rfc5322: {text!r} has an empty address")
        name = match.group("name").strip()
        return {"name": name or None, "email": email}

    if "<" in text or ">" in text:
        raise TransformError(f"parse_rfc5322: {text!r} has an unterminated address")

    if _BARE_EMAIL.match(text):
        return {"name": None, "email": text.lower()}

    # A People-picker display name with no address of its own.
    return {"name": text, "email": None}


def _split_person_entries(text: str) -> List[str]:
    """Split a person list without splitting inside a display name.

    Semicolons win when present, because ``"Smith, Jane <j@mit.edu>"`` is a single
    person whose name contains a comma. Commas are only treated as separators
    when there is no semicolon and more than one address is present.
    """
    if ";" in text:
        return text.split(";")
    if text.count("<") > 1:
        return text.split(",")
    return [text]


def parse_rfc5322_list(value: Any) -> List[Dict[str, Optional[str]]]:
    """Parse an RFC 5322-style person list into ``[{"name", "email"}, ...]``.

    Example::

        "Alice One <alice@mit.edu>; Bob Two <bob@mit.edu>"
        -> [{"name": "Alice One", "email": "alice@mit.edu"},
            {"name": "Bob Two",   "email": "bob@mit.edu"}]

    Args:
        value: The raw cell value. A list/tuple is treated as already split.

    Returns:
        One dict per person, in source order. ``[]`` when the cell is empty.

    Raises:
        TransformError: Any entry is malformed. The whole list fails rather than
            silently dropping a collaborator.
    """
    if isinstance(value, (list, tuple)):
        entries: List[Any] = list(value)
    else:
        text = _text(value, "parse_rfc5322_list")
        if text is None:
            return []
        entries = _split_person_entries(text)

    people: List[Dict[str, Optional[str]]] = []
    for entry in entries:
        person = parse_rfc5322(entry)
        if person is not None:
            people.append(person)
    return people


def sp_multiselect(value: Any) -> List[str]:
    """Split a SharePoint multi-choice cell into its selected values.

    Accepts every delimiter the export produces: SharePoint's internal ``;#``,
    plain ``;``, and ``,``.

    Args:
        value: The raw cell value. A list/tuple is passed through.

    Returns:
        The selected values, stripped and de-blanked. ``[]`` when empty.
    """
    if isinstance(value, (list, tuple)):
        return [str(v).strip() for v in value if str(v).strip()]
    text = _text(value, "sp_multiselect")
    if text is None:
        return []
    return [token.strip() for token in _MULTISELECT_SPLIT.split(text) if token.strip()]


def sp_date(value: Any) -> Optional[str]:
    """Normalize a SharePoint date string to ISO-8601.

    Tries the ``M/D/YYYY h:MM AM`` renderings the SharePoint UI and CSV export
    produce, then falls back to
    :func:`scidk.pipeline.transforms.date_parse` for ISO-8601 (including a
    trailing ``Z``) and the common unambiguous formats.

    Args:
        value: The raw cell value.

    Returns:
        The ISO-8601 string, or None when the cell is empty.

    Raises:
        TransformError: The value is not a recognizable date.
    """
    text = _text(value, "sp_date")
    if text is None:
        return None
    for fmt in _SP_DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).isoformat()
        except ValueError:
            continue
    try:
        return date_parse(text)
    except TransformError:
        raise TransformError(f"sp_date: {text!r} is not a recognizable SharePoint date") from None


def sp_yesno(value: Any) -> Optional[bool]:
    """Convert a SharePoint Yes/No column to ``bool``.

    Accepts ``Yes``/``No`` alongside the ``true``/``false`` and ``1``/``0``
    renderings the export uses interchangeably, case-insensitively.

    Args:
        value: The raw cell value.

    Returns:
        True/False, or None when the cell is empty.

    Raises:
        TransformError: The value is not a recognizable Yes/No.
    """
    text = _text(value, "sp_yesno")
    if text is None:
        return None
    try:
        return boolean_coerce(text)
    except TransformError:
        raise TransformError(f"sp_yesno: {text!r} is not a Yes/No value") from None


def sp_colresolution(prefer_col: str, fallback_col: str, row: Mapping[str, Any]) -> Optional[str]:
    """Resolve a ``_sp`` / ``_orig`` column pair, preferring the current value.

    The AIPT list carries both the live SharePoint column (``StudyType_sp``) and
    the value migrated from Drupal (``StudyType_orig``). The current SharePoint
    value wins; the legacy value fills the gap for rows SharePoint never owned.

    Unlike the other transforms this one reads the whole row, because resolving a
    column pair is a choice *between* columns. It is still pure.

    Args:
        prefer_col: Column consulted first (typically the ``_sp`` variant).
        fallback_col: Column used when ``prefer_col`` is absent or blank.
        row: The raw row.

    Returns:
        The first non-empty value, or None when both are empty — so the caller
        omits the property rather than writing a blank.

    Raises:
        TransformError: ``row`` is not a mapping.
    """
    if not isinstance(row, Mapping):
        raise TransformError(
            f"sp_colresolution: expected a row mapping, got {type(row).__name__}"
        )
    for col in (prefer_col, fallback_col):
        if not col:
            continue
        value = row.get(col)
        text = value.strip() if isinstance(value, str) else ("" if value is None else str(value).strip())
        if text:
            return text
    return None


#: The SharePoint-specific transforms, exactly as published by
#: ``SharePointPlugin.transform_library()``.
SHAREPOINT_TRANSFORMS: Dict[str, Callable] = {
    "parse_rfc5322": parse_rfc5322,
    "parse_rfc5322_list": parse_rfc5322_list,
    "sp_multiselect": sp_multiselect,
    "sp_date": sp_date,
    "sp_yesno": sp_yesno,
    "sp_colresolution": sp_colresolution,
}
